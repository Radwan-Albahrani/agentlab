"""Agents are ready only when they answer (#18): apply waits for their health checks and names the one that isn't,
doctor reports a stuck start, and with Coolify each agent is taken off Coolify's network as soon as its deploy settles
while the agent waits for exactly that before its first downloads."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentlab import config, deploy, health, render, util
from test_updates import resolve


def state_json(status='running', health_status='healthy', output='', exit_code=0):
    st = {'Status': status, 'ExitCode': exit_code}
    if health_status:
        st['Health'] = {'Status': health_status, 'Log': [{'Output': output}] if output else []}
    return json.dumps(st)


class State(unittest.TestCase):
    def setUp(self):
        self.cfg = resolve()
        self.sara = self.cfg['agents'][0]

    def state(self, ids, inspect=''):
        with (
            mock.patch.object(health.deploy, 'containers', return_value=ids),
            mock.patch.object(health, 'run', return_value=(0, inspect)),
        ):
            return health.state(self.cfg, self.sara)

    def test_healthy_starting_unhealthy(self):
        self.assertEqual(self.state(['c1'], state_json()), ('healthy', ''))
        self.assertEqual(self.state(['c1'], state_json(health_status='starting'))[0], 'starting')
        s, detail = self.state(['c1'], state_json(health_status='unhealthy', output='curl: (7) Failed to connect\n'))
        self.assertEqual((s, detail), ('unhealthy', 'curl: (7) Failed to connect'))

    def test_exited_and_missing(self):
        self.assertEqual(self.state(['c1'], state_json('exited', exit_code=137)), ('exited', 'exited (exit 137)'))
        self.assertEqual(self.state([]), ('missing', 'no container'))


class WaitReady(unittest.TestCase):
    def setUp(self):
        self.cfg = resolve()
        self.now = [0.0]

    def wait(self, sequence, timeout_s=600):
        """sequence: one {agent id: (state, detail)} per poll; the last repeats."""
        polls = iter(sequence)
        current = [sequence[0]]

        def state(_cfg, agent):
            return current[0][agent['id']]

        def sleep(s):
            self.now[0] += s
            current[0] = next(polls, current[0])

        said = []
        with mock.patch.object(health, 'state', side_effect=state), mock.patch.object(health, 'say', said.append):
            health.wait_ready(self.cfg, timeout_s, sleep=sleep, clock=lambda: self.now[0])
        return ' | '.join(said)

    def test_returns_once_everyone_answers(self):
        start = {'sara': ('starting', ''), 'omar': ('healthy', '')}
        done = {'sara': ('healthy', ''), 'omar': ('healthy', '')}
        out = self.wait([start, start, done])
        self.assertIn('waiting for sara', out)

    def test_slow_first_start_that_looks_unhealthy_still_gets_its_time(self):
        slow = {'sara': ('unhealthy', 'T3 not answering yet'), 'omar': ('healthy', '')}
        self.wait([slow, slow, {'sara': ('healthy', ''), 'omar': ('healthy', '')}])

    def test_names_the_agent_that_never_comes_up(self):
        stuck = {'sara': ('starting', 'still installing'), 'omar': ('healthy', '')}
        with self.assertRaises(util.Failed) as e:
            self.wait([stuck], timeout_s=60)
        self.assertIn('sara: starting (still installing)', str(e.exception))
        self.assertNotIn('omar', str(e.exception))

    def test_a_gone_container_fails_at_once(self):
        with self.assertRaises(util.Failed) as e:
            self.wait([{'sara': ('exited', 'exited (exit 1)'), 'omar': ('healthy', '')}])
        self.assertEqual(self.now[0], 0)
        self.assertIn('sara: exited', str(e.exception))


class DoctorCheck(unittest.TestCase):
    def checks(self, states):
        from agentlab import doctor  # noqa: PLC0415

        c = doctor.Checks()
        with mock.patch.object(health, 'state', side_effect=lambda _cfg, a: states[a['id']]):
            health.checks(resolve(), c)
        return {i['id']: i for i in c.items}

    def test_ok_warning_error(self):
        items = self.checks({'sara': ('starting', ''), 'omar': ('unhealthy', 'T3 not answering')})
        self.assertEqual(items['agent-health-sara']['severity'], 'warning')
        self.assertIn('still starting', items['agent-health-sara']['message'])
        self.assertEqual(items['agent-health-omar']['severity'], 'error')
        self.assertIn('T3 not answering', items['agent-health-omar']['message'])
        self.assertTrue(self.checks({'sara': ('healthy', ''), 'omar': ('healthy', '')})['agent-health-sara']['ok'])


class NetworkWait(unittest.TestCase):
    def test_only_coolify_agents_wait_for_their_own_address(self):
        for mode, expect_wait in (('compose', False), ('coolify', True)):
            extra = '\n[coolify]\nurl = "http://127.0.0.1:8000"\ntoken_file = "/x"\n' if mode == 'coolify' else ''
            cfg = resolve(extra=extra)
            cfg['deploy'] = mode
            sara = cfg['agents'][0]
            env = render.agent(cfg, sara)['services']['agent']['environment']
            self.assertEqual(env['AGENTLAB_WAIT_NETWORK'], config.agent_ip(sara) if expect_wait else '')


class PromptIsolation(unittest.TestCase):
    """A deployed agent is taken off Coolify's network as soon as its stack settles, not at the end of apply."""

    def test_isolates_the_agent_right_after_it_settles(self):
        tmp = tempfile.mkdtemp()
        cfg = resolve(data=tmp)
        stack = 'agentlab-agent-sara'
        os.makedirs(deploy.stack_folder(cfg, stack))
        with open(deploy.compose_file(cfg, stack), 'w') as f:
            f.write('services:\n  agent:\n    image: x\n')
        calls = []
        with (
            mock.patch.object(deploy, 'why_deploy', return_value=('its file changed', '')),
            mock.patch.object(deploy, 'settle', side_effect=lambda *a, **k: calls.append('settle')),
            mock.patch.object(
                deploy,
                'isolate',
                side_effect=lambda _c, _p, agents=None: calls.append(('isolate', [a['id'] for a in agents])),
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            plan = mock.Mock(dry=False)
            deploy.deploy(cfg, stack, 'agent', 'sara', plan)
        self.assertEqual(calls, ['settle', ('isolate', ['sara'])])
        deploy.DEPLOYED.discard(stack)


if __name__ == '__main__':
    unittest.main()
