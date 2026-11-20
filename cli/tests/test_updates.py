import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentlab import apply, config, coolify, deploy, fsm, render, update, util

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


SETTLED = ('completed', 'cancelled', 'failed', 'interrupted', 'rolled_back')


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
        # the container was created at 16:00 UTC, the image rebuilt at 16:47:59 UTC
        self.image_now = '2026-11-02T19:47:59.480512677+03:00'
        self.t3 = {}  # agent id -> its T3 runs [(run id, thread id, status)], as its agent-t3 reports them
        self.enterContext(mock.patch('agentlab.deploy.run', self.docker))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def runs(self, agent, rows):
        self.t3[agent['id']] = list(rows)

    def set_status(self, agent, status, where='running'):
        self.t3[agent['id']] = [(r, t, status if s == where else s) for r, t, s in self.t3[agent['id']]]

    def docker(self, cmd, check=True, **_):
        if cmd[:2] == ['docker', 'ps']:  # the container of a stack: c-<its compose project>
            return 0, 'c-' + cmd[cmd.index('--filter') + 1].rsplit('=', 1)[1]
        if cmd[:2] == ['docker', 'exec'] and cmd[-2] == 'agent-t3':
            live = [[r, t] for r, t, s in self.t3.get(cmd[4].removeprefix('c-agentlab-agent-'), []) if s not in SETTLED]
            return 0, json.dumps(bool(live) if cmd[-1] == 'busy' else live)
        if cmd[:2] == ['docker', 'inspect']:
            return 0, 'agentlab/agent:latest 2026-11-02T16:00:00.5Z'
        if cmd[:3] == ['docker', 'image', 'inspect']:
            return 0, self.image_now
        return 0, ''


class ImageRedeploy(Stack):
    def test_a_newer_image_redeploys_an_idle_agent(self):
        self.runs(self.sara, [('r1', 't1', 'completed')])
        why = deploy.why_deploy(self.cfg, self.stack, self.text)
        self.assertEqual(why, ('newer', 'agentlab/agent:latest'))
        self.assertEqual((why.deploys(), why.note(), why.skip()), (True, ' (newer image: agentlab/agent:latest)', ''))

    def test_same_image_changes_nothing(self):
        self.image_now = '2026-11-02T18:59:00+03:00'
        why = deploy.why_deploy(self.cfg, self.stack, self.text)
        self.assertEqual((why, why.deploys(), why.note(), why.skip()), (('current', ''), False, '', ''))

    def test_unreadable_times_never_count_as_newer(self):
        self.image_now = 'not a time'
        self.assertEqual(deploy.why_deploy(self.cfg, self.stack, self.text), ('current', ''))

    def test_never_mid_turn_unless_forced(self):
        self.runs(self.sara, [('r1', 't1', 'running')])
        why = deploy.why_deploy(self.cfg, self.stack, self.text)
        self.assertEqual((why, why.deploys()), (('busy', 'sara'), False))
        self.assertEqual(why.skip(), 'sara busy (a T3 turn is running); its new image goes live on the next apply')
        forced = deploy.why_deploy(self.cfg, self.stack, self.text, force=True)
        self.assertEqual((forced, forced.deploys(), forced.note()), (('asked', ''), True, ''))

    def test_a_changed_file_or_no_containers_deploys_without_a_note(self):
        self.runs(self.sara, [])
        self.assertEqual(deploy.why_deploy(self.cfg, self.stack, self.text + '\n'), ('changed', ''))
        with mock.patch.object(deploy, 'containers', return_value=[]):
            why = deploy.why_deploy(self.cfg, self.stack, self.text)
        self.assertEqual((why, why.deploys(), why.note()), (('stopped', ''), True, ''))

    def test_dry_run_plans_it_with_the_reason(self):
        plan = util.Plan(dry=True)
        start = len(util.OUT.changes)
        self.runs(self.sara, [])
        deploy.deploy(self.cfg, self.stack, 'agent', 'sara', plan)
        self.assertEqual(util.OUT.changes[start]['change'], f'deploy {self.stack} (newer image: agentlab/agent:latest)')


class AskT3(unittest.TestCase):
    """The host asks the agent (agent-t3 in its container); it never opens the agent's database."""

    def setUp(self):
        self.cfg = resolve()
        self.sara = self.cfg['agents'][0]
        self.calls = []

    def ask(self, running=True, rc=0, out='', timeout=False):
        def docker(cmd, check=True, **_):
            self.calls.append(cmd)
            if cmd[:2] == ['docker', 'ps']:
                return 0, 'c1' if running else ''
            if timeout:
                raise subprocess.TimeoutExpired(cmd, 60)
            return rc, out

        with mock.patch('agentlab.deploy.run', docker):
            return deploy.agent_busy(self.cfg, self.sara), update.inflight(self.cfg, self.sara)

    def test_asks_the_running_container_as_the_agent(self):
        self.assertEqual(self.ask(out='true'), (True, []))
        self.assertEqual(self.calls[1], ['docker', 'exec', '-u', 'agent', 'c1', 'agent-t3', 'busy'])
        self.assertEqual(self.calls[3][-1], 'inflight')
        self.assertIn('label=com.docker.compose.service=agent', self.calls[0])
        self.assertEqual(self.ask(out='false'), (False, []))
        self.assertEqual(self.ask(out='[["r1", "t1"], ["r2", "t1"]]')[1], [('r1', 't1'), ('r2', 't1')])

    def test_a_stopped_agent_has_nothing_in_progress(self):
        self.assertEqual(self.ask(running=False), (False, []))
        self.assertEqual(len(self.calls), 2)  # no exec

    def test_no_answer_counts_as_busy_with_nothing_known_in_flight(self):
        self.assertEqual(self.ask(rc=1, out='agent-t3: database is locked'), (True, []))
        self.assertEqual(self.ask(rc=126, out='OCI runtime exec failed'), (True, []))
        self.assertEqual(self.ask(out='Traceback ...'), (True, []))
        self.assertEqual(self.ask(out='{"busy": 1}'), (True, []))
        self.assertEqual(self.ask(out='[["r1"]]'), (True, []))
        self.assertEqual(self.ask(timeout=True), (True, []))


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
        self.runs(self.sara, [('r1', 't1', 'completed')])
        self.runs(self.omar, [('r2', 't2', 'running')])

        def tick(n):
            if n == 3:
                self.set_status(self.omar, 'completed')

        updated, deferred, _ = self.wait('defer', tick)
        self.assertEqual(updated, ['sara', 'omar'])
        self.assertEqual(self.deployed, ['agentlab-agent-sara', 'agentlab-agent-omar'])
        self.assertEqual(deferred, [])

    def test_still_busy_at_the_end_is_deferred(self):
        self.runs(self.sara, [])
        self.runs(self.omar, [('r2', 't2', 'running')])
        updated, deferred, resumed = self.wait('defer', lambda n: None)
        self.assertEqual((updated, deferred, resumed), (['sara'], ['omar'], {}))
        self.assertGreaterEqual(self.clock.t - 1_000_000.0, 4 * 3600)
        self.assertNotIn('agentlab-agent-omar', self.deployed)

    def test_resume_restarts_and_leaves_the_cut_off_turns_to_t3(self):
        self.runs(self.sara, [])
        rows = [('r1', 't1', 'running'), ('r2', 't2', 'running'), ('r3', 't3', 'completed'), ('r4', 't1', 'running')]
        self.runs(self.omar, rows)
        updated, deferred, resumed = self.wait('resume', lambda n: None)
        self.assertEqual(updated, ['sara', 'omar'])
        self.assertEqual(deferred, [])
        self.assertEqual(resumed, {'omar': ['t1', 't2']})
        self.assertEqual(self.deployed, ['agentlab-agent-sara', 'agentlab-agent-omar'])

    def test_resume_now_does_not_wait(self):
        self.runs(self.sara, [])
        self.runs(self.omar, [('r2', 't2', 'running')])
        slept = []
        updated, deferred, _ = update.wait_for_agents(
            self.cfg, util.Plan(False), 0, 'resume', sleep=slept.append, clock=self.clock
        )
        self.assertEqual((updated, deferred, slept), (['sara', 'omar'], [], []))

    def test_each_agent_leaves_pending_once(self):
        self.runs(self.sara, [])
        self.runs(self.omar, [('r2', 't2', 'running')])
        moves, real = [], update.STEP.to
        with mock.patch.object(update.STEP, 'to', side_effect=lambda s, new: moves.append((s, new)) or real(s, new)):
            self.wait('defer', lambda n: None)
        self.assertEqual(moves, [('pending', 'updated'), ('pending', 'deferred')])

    def test_a_step_once_taken_is_final(self):
        for old, new in (
            ('updated', 'deferred'),
            ('deferred', 'resumed'),
            ('resumed', 'updated'),
            ('pending', 'pending'),
        ):
            with self.subTest(old=old, new=new), self.assertRaises(fsm.IllegalStateError):
                update.STEP.to(old, new)
        with self.assertRaises(fsm.IllegalStateError):
            update.STEP.of('waiting')
        with self.assertRaises(fsm.IllegalStateError):  # every state a move leads to is named
            fsm.Machine('x', {'a': ('b',)})


class HostServices(unittest.TestCase):
    def restarts(self, changed):
        calls = []

        def fake(cmd, **_):
            calls.append(cmd)
            if cmd[1] == 'show':
                return 0, {'agentlab-watch.service': '@1000', 'agentlab-throttle.service': '@3000'}[cmd[-1]]
            return 0, ''

        with mock.patch('agentlab.apply.run', fake), mock.patch('agentlab.util.run', fake):
            apply.host_services(util.Plan(False), changed)
        return [c[-1] for c in calls if c[1] == 'restart']

    def test_only_services_older_than_their_code_restart(self):
        self.assertEqual(self.restarts(2000), ['agentlab-watch.service'])
        self.assertEqual(self.restarts(500), [])

    def test_the_code_time_is_the_newest_python_file(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(f'{d}/watch/__pycache__')
            for name, t in (('cluster.py', 100), ('watch/store.py', 200), ('watch/__pycache__/x.py', 900)):
                open(f'{d}/{name}', 'w').close()
                os.utime(f'{d}/{name}', (t, t))
            self.assertEqual(apply.code_changed_at(d), 200)


class OncePerRun(Waiting):
    def test_a_stack_apply_deployed_is_not_deployed_again(self):
        deploy.DEPLOYED.add('agentlab-agent-sara')
        self.runs(self.sara, [])
        self.runs(self.omar, [])
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

    def settle(self, kind='agent', timeout_s=60, on_stuck=None):
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
            deploy.settle(
                self.cfg, 'agentlab-agent-sara', kind, AGENT_TEXT, timeout_s, sleep, lambda: self.t, on_stuck=on_stuck
            )

    def test_a_container_docker_could_not_start_fails_at_once_with_its_error(self):
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

    def test_an_old_container_that_still_stands_gets_one_replacement(self):
        stuck = self.rows(
            ('agent-x', 'running', 'Up 3 days (unhealthy)', 'agent', 'old999'),
            ('files-x', 'running', 'Up', 'files', 'abc123'),
        )
        fresh = self.rows(
            ('agent-x', 'running', 'Up 1 second', 'agent', 'abc123'), ('files-x', 'running', 'Up', 'files', 'abc123')
        )
        self.views = [stuck] * 40 + [fresh]
        replaced = []
        with mock.patch('agentlab.deploy.warn'):
            self.settle(timeout_s=20 * 60, on_stuck=replaced.append)
        self.assertEqual(replaced, [['agent-x']])
        self.assertGreaterEqual(self.t, deploy.STUCK_S)

    def test_force_remove_kills_the_shim_of_a_container_that_never_exits(self):
        cid = 'a' * 64
        calls = []

        def run(cmd, **_):
            calls.append(cmd)
            if cmd[:2] == ['docker', 'rm']:
                tries = sum(c[:2] == ['docker', 'rm'] for c in calls)
                return (0, '') if tries > 1 else (1, 'did not receive an exit event')
            if cmd[:2] == ['docker', 'inspect']:
                return 0, cid
            if cmd[0] == 'pgrep':
                return 0, '4242'
            return 0, ''

        with mock.patch('agentlab.deploy.run', run), mock.patch('agentlab.deploy.warn') as warned:
            deploy.force_remove('agent-x')
        self.assertIn(['kill', '-9', '4242'], calls)
        self.assertIn(f'-id {cid}', ' '.join(next(c for c in calls if c[0] == 'pgrep')))
        self.assertIn('reboot', warned.call_args.args[0])

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
