"""Self-maintenance: [updates] config, apply redeploying on a newer image (but never mid-turn), `agentctl update`'s
fast-forward-only pull, and how it waits for busy agents, defers them, or restarts and resumes their chats."""

import contextlib
import io
import os
import sqlite3
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentlab import config, deploy, render, update, util

BASE = """
[cluster]
name = "test"
domain = "agents.example.com"
hub_domain = "agents-hub.example.com"
data = "{data}"
deploy = "compose"

[auth]
mode = "none"
admins = ["sara@example.com"]

[[agents]]
id = "sara"
owner = "sara@example.com"

[[agents]]
id = "omar"
owner = "omar@example.com"
"""


def resolve(data='/srv/agentlab', extra=''):
    return config.resolve(tomllib.loads(BASE.format(data=data) + extra))


def runs_db(agent, rows):
    """T3's runs table at the agent's real host path: [(run id, thread id, status)]."""
    folder = os.path.join(agent['path'], 'home', '.t3', 'userdata')
    os.makedirs(folder, exist_ok=True)
    db = os.path.join(folder, 'statev2.sqlite')
    with sqlite3.connect(db) as c:
        c.execute(
            'create table if not exists orchestration_v2_projection_runs (run_id text, thread_id text, status text)'
        )
        c.execute('delete from orchestration_v2_projection_runs')
        c.executemany('insert into orchestration_v2_projection_runs values (?, ?, ?)', rows)
    return db


def set_status(agent, status, where='running'):
    db = os.path.join(agent['path'], 'home', '.t3', 'userdata', 'statev2.sqlite')
    with sqlite3.connect(db) as c:
        c.execute('update orchestration_v2_projection_runs set status = ? where status = ?', (status, where))


class Config(unittest.TestCase):
    def test_defaults_and_agent_env(self):
        cfg = resolve()
        self.assertEqual(cfg['updates']['agentlab'], 'off')
        self.assertEqual(cfg['updates']['on_busy'], 'defer')
        env = render.agent(cfg, cfg['agents'][0])['services']['agent']['environment']
        self.assertEqual(
            (env['AGENTLAB_UPDATE_HOURS'], env['AGENTLAB_UPDATE_WAIT_HOURS'], env['AGENTLAB_ON_BUSY']),
            ('6', '4', 'defer'),
        )

    def test_bad_values_are_named(self):
        bad = '\n[updates]\nagentlab = "weekly"\ntime = "25:00"\non_busy = "kill"\nwait_hours = -1\n'
        with self.assertRaises(util.Failed) as e:
            resolve(extra=bad)
        for words in ('agentlab must be', 'time must be', 'on_busy must be', 'wait_hours must be'):
            self.assertIn(words, str(e.exception))


class Stack(unittest.TestCase):
    """A rendered, deployed agent stack in a throwaway data dir, with Docker faked."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = resolve(self.tmp.name)
        self.sara = self.cfg['agents'][0]
        self.stack = 'agentlab-agent-sara'
        os.makedirs(deploy.stack_folder(self.cfg, self.stack))
        self.text = 'services: {}\n'
        with open(deploy.compose_file(self.cfg, self.stack), 'w') as f:
            f.write(self.text)
        deploy.mark_deployed(self.cfg, self.stack, self.text)
        self.image_now = 'sha256:new'
        self.enterContext(mock.patch('agentlab.deploy.run', self.docker))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def docker(self, cmd, check=True):
        if cmd[:2] == ['docker', 'ps']:
            return 0, 'c1'
        if cmd[:2] == ['docker', 'inspect']:
            return 0, 'agentlab/agent:latest sha256:old'
        if cmd[:3] == ['docker', 'image', 'inspect']:
            return 0, self.image_now
        return 0, ''


class ImageRedeploy(Stack):
    def test_a_newer_image_redeploys_an_idle_agent(self):
        runs_db(self.sara, [('r1', 't1', 'completed')])
        reason, skip = deploy.why_deploy(self.cfg, self.stack, self.text)
        self.assertEqual((reason, skip), ('newer image: agentlab/agent:latest', ''))

    def test_same_image_changes_nothing(self):
        self.image_now = 'sha256:old'
        self.assertEqual(deploy.why_deploy(self.cfg, self.stack, self.text), ('', ''))

    def test_never_mid_turn_unless_forced(self):
        runs_db(self.sara, [('r1', 't1', 'running')])
        reason, skip = deploy.why_deploy(self.cfg, self.stack, self.text)
        self.assertEqual(reason, '')
        self.assertIn('sara busy', skip)
        self.assertEqual(deploy.why_deploy(self.cfg, self.stack, self.text, force=True)[0], 'asked for')

    def test_dry_run_plans_it_with_the_reason(self):
        plan = util.Plan(dry=True)
        start = len(util.OUT.changes)
        runs_db(self.sara, [])
        deploy.deploy(self.cfg, self.stack, 'agent', 'sara', plan)
        self.assertEqual(util.OUT.changes[start]['change'], f'deploy {self.stack} (newer image: agentlab/agent:latest)')


class Pull(unittest.TestCase):
    def fake_git(self, answers):
        calls = []

        def run(cmd, check=True):
            sub = cmd[3]
            calls.append(sub)
            rc, out = answers.get(sub, (0, ''))
            if rc and check:
                raise util.Failed(f'git {sub} failed')
            return rc, out

        return run, calls

    def test_fast_forwards(self):
        heads = iter(['aaa', 'bbb'])
        run, calls = self.fake_git({})
        with mock.patch('agentlab.update.run', run), mock.patch('agentlab.update.head', lambda: next(heads)):
            self.assertEqual(update.pull('main'), ('aaa', 'bbb'))
        self.assertEqual(calls[-1], 'merge')

    def test_refuses_local_changes(self):
        run, calls = self.fake_git({'status': (0, ' M cli/agentctl\n')})
        with mock.patch('agentlab.update.run', run), self.assertRaises(util.Failed) as e:
            update.pull('main')
        self.assertIn('local changes', str(e.exception))
        self.assertNotIn('merge', calls)

    def test_refuses_a_diverged_branch(self):
        run, calls = self.fake_git({'merge-base': (1, '')})
        with (
            mock.patch('agentlab.update.run', run),
            mock.patch('agentlab.update.head', return_value='aaa'),
            self.assertRaises(util.Failed) as e,
        ):
            update.pull('main')
        self.assertIn('cannot fast-forward', str(e.exception))
        self.assertNotIn('merge', calls)

    def test_refuses_a_copy_that_is_not_a_checkout(self):
        run, _ = self.fake_git({'rev-parse': (128, 'not a git repository')})
        with mock.patch('agentlab.update.run', run), self.assertRaises(util.Failed) as e:
            update.pull('main')
        self.assertIn('not a git checkout', str(e.exception))


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


class Waiting(Stack):
    def setUp(self):
        super().setUp()
        self.omar = self.cfg['agents'][1]
        os.makedirs(deploy.stack_folder(self.cfg, 'agentlab-agent-omar'))
        with open(deploy.compose_file(self.cfg, 'agentlab-agent-omar'), 'w') as f:
            f.write(self.text)
        deploy.mark_deployed(self.cfg, 'agentlab-agent-omar', self.text)
        self.deployed = []
        self.enterContext(mock.patch('agentlab.deploy.deploy', lambda cfg, stack, *a, **k: self.deployed.append(stack)))
        self.enterContext(mock.patch('agentlab.deploy.isolate'))
        self.clock = Clock()

    def wait(self, on_busy, ticks):
        """Run the wait loop; `ticks(n)` runs at each 5-minute check."""
        n = [0]

        def sleep(_):
            n[0] += 1
            self.clock.t += update.CHECK_EVERY_S
            ticks(n[0])

        return update.wait_for_agents(self.cfg, util.Plan(False), 4, on_busy, sleep=sleep, clock=self.clock)

    def test_idle_agents_go_at_once_and_busy_ones_as_soon_as_they_are_idle(self):
        runs_db(self.sara, [('r1', 't1', 'completed')])
        runs_db(self.omar, [('r2', 't2', 'running')])

        def tick(n):
            if n == 3:
                set_status(self.omar, 'completed')

        updated, deferred, _ = self.wait('defer', tick)
        self.assertEqual(updated, ['sara', 'omar'])
        self.assertEqual(self.deployed, ['agentlab-agent-sara', 'agentlab-agent-omar'])
        self.assertEqual(deferred, [])

    def test_still_busy_at_the_end_is_deferred(self):
        runs_db(self.sara, [])
        runs_db(self.omar, [('r2', 't2', 'running')])
        updated, deferred, resumed = self.wait('defer', lambda n: None)
        self.assertEqual((updated, deferred, resumed), (['sara'], ['omar'], {}))
        self.assertGreaterEqual(self.clock.t - 1_000_000.0, 4 * 3600)
        self.assertNotIn('agentlab-agent-omar', self.deployed)

    def test_resume_restarts_and_tells_only_interrupted_chats(self):
        runs_db(self.sara, [])
        rows = [('r1', 't1', 'running'), ('r2', 't2', 'running'), ('r3', 't3', 'completed'), ('r4', 't1', 'running')]
        runs_db(self.omar, rows)
        told = []

        def restart(cfg, stack, *a, **k):  # the restart cuts off what was running, the way T3 marks it on start
            self.deployed.append(stack)
            if stack == 'agentlab-agent-omar':
                set_status(self.omar, 'interrupted')

        with (
            mock.patch('agentlab.deploy.deploy', restart),
            mock.patch('agentlab.update.wait_healthy', return_value='c9'),
            mock.patch('agentlab.update.send_continue', lambda cid, thread: told.append((cid, thread)) or True),
        ):
            updated, deferred, resumed = self.wait('resume', lambda n: None)
        self.assertEqual(updated, ['sara', 'omar'])
        self.assertEqual(deferred, [])
        self.assertEqual(resumed, {'omar': ['t1', 't2']})
        self.assertEqual(told, [('c9', 't1'), ('c9', 't2')])


class Record(unittest.TestCase):
    def test_last_run_is_kept_for_status_and_doctor(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = resolve(d)
            update.record(cfg, scheduled=True, result='deferred', agents_deferred=['omar'])
            last = update.last(cfg)
            self.assertEqual((last['result'], last['agents_deferred']), ('deferred', ['omar']))
            self.assertIn('at', last)


if __name__ == '__main__':
    unittest.main()
