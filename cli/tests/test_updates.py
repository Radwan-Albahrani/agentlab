"""Self-maintenance: [updates] config, apply redeploying on a newer image (but never mid-turn), `agentctl update`'s
fast-forward-only pull, and how it waits for busy agents, defers them, or restarts and resumes their chats."""

import contextlib
import io
import os
import re
import sqlite3
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentlab import config, coolify, deploy, render, update, util

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
        # times as Docker prints them; the container was created at 16:00 UTC, the image rebuilt at 16:47:59 UTC
        self.image_now = '2026-11-02T19:47:59.480512677+03:00'
        self.enterContext(mock.patch('agentlab.deploy.run', self.docker))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def docker(self, cmd, check=True):
        if cmd[:2] == ['docker', 'ps']:
            return 0, 'c1'
        if cmd[:2] == ['docker', 'inspect']:
            return 0, 'agentlab/agent:latest 2026-11-02T16:00:00.5Z'
        if cmd[:3] == ['docker', 'image', 'inspect']:
            return 0, self.image_now
        return 0, ''


class ImageRedeploy(Stack):
    def test_a_newer_image_redeploys_an_idle_agent(self):
        runs_db(self.sara, [('r1', 't1', 'completed')])
        reason, skip = deploy.why_deploy(self.cfg, self.stack, self.text)
        self.assertEqual((reason, skip), ('newer image: agentlab/agent:latest', ''))

    def test_same_image_changes_nothing(self):
        # a cached rebuild keeps the image's old creation time, whatever ids the image store reports
        self.image_now = '2026-11-02T18:59:00+03:00'
        self.assertEqual(deploy.why_deploy(self.cfg, self.stack, self.text), ('', ''))

    def test_unreadable_times_never_count_as_newer(self):
        self.image_now = 'not a time'
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
        deploy.DEPLOYED.clear()
        self.addCleanup(deploy.DEPLOYED.clear)
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

    def test_resume_restarts_and_leaves_the_cut_off_turns_to_t3(self):  # T3 resumes them itself on start
        runs_db(self.sara, [])
        rows = [('r1', 't1', 'running'), ('r2', 't2', 'running'), ('r3', 't3', 'completed'), ('r4', 't1', 'running')]
        runs_db(self.omar, rows)
        updated, deferred, resumed = self.wait('resume', lambda n: None)
        self.assertEqual(updated, ['sara', 'omar'])
        self.assertEqual(deferred, [])
        self.assertEqual(resumed, {'omar': ['t1', 't2']})
        self.assertEqual(self.deployed, ['agentlab-agent-sara', 'agentlab-agent-omar'])

    def test_resume_now_does_not_wait(self):  # agentctl update --resume
        runs_db(self.sara, [])
        runs_db(self.omar, [('r2', 't2', 'running')])
        slept = []
        updated, deferred, _ = update.wait_for_agents(
            self.cfg, util.Plan(False), 0, 'resume', sleep=slept.append, clock=self.clock
        )
        self.assertEqual((updated, deferred, slept), (['sara', 'omar'], [], []))


class OncePerRun(Waiting):
    def test_a_stack_apply_deployed_is_not_deployed_again(self):
        # the home lab saw two concurrent Coolify deploys per agent: apply's, then the wait loop's while the first was
        # still recreating (old containers still looked out of date)
        deploy.DEPLOYED.add('agentlab-agent-sara')
        runs_db(self.sara, [])
        runs_db(self.omar, [])
        updated, _, _ = self.wait('defer', lambda n: None)
        self.assertEqual(updated, ['omar'])
        self.assertEqual(self.deployed, ['agentlab-agent-omar'])


AGENT_TEXT = """# agentlab-agent-sara.
services:
  agent:
    image: agentlab/agent:latest
    labels:
      agentlab.rendered: "abc123"
  files:
    image: x
    labels:
      agentlab.rendered: "abc123"
"""


class Settle(unittest.TestCase):
    """After a deploy, every service runs in a container from this render, or the deploy fails loudly."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = resolve(self.tmp.name)
        self.views = []
        self.slept = 0
        self.t = 0.0
        self.errors = {}  # container name -> the error Docker recorded starting it

    def rows(self, *rows):
        return [dict(zip(('name', 'state', 'status', 'service', 'rendered'), r, strict=True)) for r in rows]

    def settle(self, kind='agent', timeout_s=60):
        views = iter(self.views)
        last = [[]]

        def seen(cfg, stack):
            last[0] = next(views, last[0])
            return last[0]

        def sleep(s):
            self.slept += 1
            self.t += s

        with (
            mock.patch('agentlab.deploy.stack_containers', seen),
            mock.patch('agentlab.deploy.docker_error', lambda name: self.errors.get(name, '')),
        ):
            deploy.settle(self.cfg, 'agentlab-agent-sara', kind, AGENT_TEXT, timeout_s, sleep, lambda: self.t)

    def test_a_container_docker_could_not_start_fails_at_once_with_its_error(self):
        # #22: the edge stayed Created because its port was taken; that never resolves by waiting
        self.views = [
            self.rows(
                ('agent-x', 'created', 'Created', 'agent', 'abc123'), ('files-x', 'running', 'Up', 'files', 'abc123')
            )
        ]
        self.errors = {'agent-x': 'Bind for 0.0.0.0:80 failed: port is already allocated'}
        with self.assertRaises(util.Failed) as e:
            self.settle()
        self.assertEqual(self.slept, 0)
        self.assertIn('failed to start', str(e.exception))
        self.assertIn('port is already allocated', str(e.exception))

    def test_waits_until_every_service_runs(self):
        created = self.rows(
            ('agent-x', 'created', 'Created', 'agent', 'abc123'), ('files-x', 'created', 'Created', 'files', 'abc123')
        )
        running = self.rows(
            ('agent-x', 'running', 'Up 2 seconds', 'agent', 'abc123'), ('files-x', 'running', 'Up', 'files', 'abc123')
        )
        self.views = [created, created, running]
        self.settle()
        self.assertEqual(self.slept, 2)

    def test_created_but_never_running_fails_with_the_states(self):
        self.views = [
            self.rows(
                ('agent-x', 'created', 'Created', 'agent', 'abc123'), ('files-x', 'running', 'Up', 'files', 'abc123')
            )
        ]
        with self.assertRaises(util.Failed) as e:
            self.settle()
        self.assertIn('did not come up', str(e.exception))
        self.assertIn('agent-x created', str(e.exception))

    def test_old_containers_and_leftovers_do_not_count(self):
        old = self.rows(
            ('agent-x', 'running', 'Up 3 days', 'agent', 'old999'), ('files-x', 'running', 'Up', 'files', 'abc123')
        )
        leftover = self.rows(
            ('f7f906c03f57_agent-x', 'running', 'Up', 'agent', 'abc123'),
            ('files-x', 'running', 'Up', 'files', 'abc123'),
        )
        self.views = [old, leftover]
        with self.assertRaises(util.Failed):
            self.settle(timeout_s=20)

    def test_leftovers_are_reported_once_the_stack_is_up(self):
        self.views = [
            self.rows(
                ('f7f906c03f57_agent-x', 'exited', 'Exited (0)', 'agent', 'abc123'),
                ('agent-x', 'running', 'Up', 'agent', 'abc123'),
                ('files-x', 'running', 'Up', 'files', 'abc123'),
            )
        ]
        with mock.patch('agentlab.deploy.warn') as warn:
            self.settle()
        self.assertIn('f7f906c03f57_agent-x', warn.call_args.args[0])

    def test_an_unconfigured_companion_counts_as_up(self):
        self.views = [
            self.rows(
                ('c-x', 'exited', 'Exited (0) 5 seconds ago', 'agent', 'abc123'),
                ('f', 'running', 'Up', 'files', 'abc123'),
            )
        ]
        self.settle(kind='companion')

    def test_services_are_read_from_the_rendered_file(self):
        self.assertEqual(deploy.compose_services(AGENT_TEXT), {'agent', 'files'})
        self.assertEqual(render.rendered_digest(AGENT_TEXT), 'abc123')

    def test_every_rendered_service_is_stamped_with_its_render(self):
        files = render.all_files(self.cfg)
        text = files['compose/agentlab-agent-sara/docker-compose.yml']
        digest = render.rendered_digest(text)
        self.assertRegex(digest, r'^[0-9a-f]{16}$')
        stamps = re.findall(r'agentlab\.rendered: "?(\w+)', text)
        self.assertEqual(stamps, [digest] * len(deploy.compose_services(text)))


class CoolifyWait(unittest.TestCase):
    def api(self, *answers):
        replies = iter(answers)
        api = mock.Mock()
        api.call.side_effect = lambda method, path, body=None: next(replies)
        return api

    def test_waits_for_the_queued_deployment(self):
        api = self.api({'status': 'queued'}, {'status': 'in_progress'}, {'status': 'finished'})
        slept = []
        coolify.wait(api, 'agentlab-core', 'd1', 600, slept.append, lambda: 0)
        self.assertEqual(len(slept), 2)

    def test_a_failed_deployment_surfaces_coolify_log(self):
        logs = (
            '[{"output": "Pulling"}, {"output": "Error response from daemon: Conflict. The container name is in use"}]'
        )
        api = self.api({'status': 'failed', 'logs': logs})
        with self.assertRaises(util.Failed) as e:
            coolify.wait(api, 'agentlab-agent-sara', 'd1', 600, lambda s: None, lambda: 0)
        self.assertIn('Conflict', str(e.exception))

    def test_deploy_waits_only_when_coolify_gives_a_deployment_id(self):
        with tempfile.TemporaryDirectory() as d:
            with open(coolify.uuid_file(d), 'w') as f:
                f.write('svc1')
            api = mock.Mock()
            api.call.side_effect = [{}, {'deployments': [{'deployment_uuid': 'd1'}]}]
            with mock.patch('agentlab.coolify.wait') as wait:
                coolify.deploy(api, {}, 'agentlab-core', 'core', None, d, 'services: {}\n')
            wait.assert_called_once_with(api, 'agentlab-core', 'd1')
            api.call.side_effect = [{}, {'message': 'Service deployment started.'}]
            with mock.patch('agentlab.coolify.wait') as wait:
                coolify.deploy(api, {}, 'agentlab-core', 'core', None, d, 'services: {}\n')
            wait.assert_not_called()


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
