import os
import sys
import tomllib
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentlab import config, install, preflight, util

BASE = """
[cluster]
name = "test"
domain = "agents.example.com"
hub_domain = "agents-hub.example.com"
deploy = "compose"
isolation = "sysbox"

[auth]
mode = "none"
admins = ["sara@example.com"]

[android]
enabled = true

[[agents]]
id = "sara"
owner = "sara@example.com"
"""


def cfg(**changes):
    c = config.resolve(tomllib.loads(BASE))
    for path, value in changes.items():
        if '__' in path:
            section, key = path.split('__')
            c[section][key] = value
        else:
            c[path] = value
    return c


class Apt:
    def __init__(self, missing=()):
        self.missing = set(missing)

    def __call__(self, cmd, **_):
        if cmd[:2] == ['apt-cache', 'policy']:
            name = cmd[2]
            out = '' if name in self.missing else f'{name}:\n  Installed: (none)\n  Candidate: 1.0\n'
            if name in self.missing and name.startswith('openjdk'):
                out = f'{name}:\n  Installed: (none)\n  Candidate: (none)\n'
            return mock.Mock(stdout=out, returncode=0)
        return mock.Mock(stdout='', returncode=0)


class Host(unittest.TestCase):
    def setUp(self):
        for name, value in {
            'lists_empty': False,
            'wsl': False,
            'kernel': (6, 12),
        }.items():
            self.enterContext(mock.patch(f'agentlab.preflight.{name}', return_value=value))
        self.enterContext(mock.patch('agentlab.preflight.shutil.which', return_value='/usr/bin/x'))
        self.enterContext(mock.patch('agentlab.preflight.platform.machine', return_value='x86_64'))
        self.kvm = self.enterContext(mock.patch('agentlab.preflight.os.path.exists', return_value=True))

    def problems(self, c=None, apt=None):
        return preflight.problems(c or cfg(), run=apt or Apt())

    def test_a_supported_host_has_nothing_to_say(self):
        self.assertEqual(self.problems(), [])

    def test_java_is_the_newest_lts_the_host_has(self):
        self.assertEqual(preflight.jre(Apt(missing={'openjdk-17-jre-headless'})), 'openjdk-21-jre-headless')
        self.assertEqual(preflight.jre(Apt(missing={'openjdk-21-jre-headless'})), 'openjdk-25-jre-headless')
        self.assertEqual(
            preflight.jre(Apt(missing={'openjdk-21-jre-headless', 'openjdk-25-jre-headless'})),
            'openjdk-17-jre-headless',
        )

    def test_no_java_at_all_is_named_before_installing(self):
        none = Apt(missing=set(preflight.JRES))
        ids = [p[0] for p in self.problems(apt=none)]
        self.assertEqual(ids, ['host-android'])
        self.assertIn('Java 17+', self.problems(apt=none)[0][1])
        self.assertEqual(self.problems(cfg(android__enabled=False), none), [])

    def test_sysbox_needs_a_new_enough_kernel_and_not_wsl(self):
        with mock.patch('agentlab.preflight.kernel', return_value=(5, 10)):
            self.assertIn('5.12', self.problems()[0][1])
        with mock.patch('agentlab.preflight.wsl', return_value=True):
            self.assertIn('WSL', self.problems()[0][1])
        with mock.patch('agentlab.preflight.kernel', return_value=(5, 10)):
            self.assertEqual(self.problems(cfg(isolation='unconfined')), [])

    def test_android_needs_kvm(self):
        self.kvm.return_value = False
        self.assertIn('/dev/kvm', self.problems()[0][1])

    def test_install_stops_before_any_step_on_an_unsupported_host(self):
        ran = []
        with (
            mock.patch('agentlab.install.need_root'),
            mock.patch(
                'agentlab.install.preflight.problems', return_value=[('host-android', 'unsupported host: x', 'y')]
            ),
            mock.patch('agentlab.install.subprocess.run', side_effect=lambda *a, **k: ran.append(a)),
            self.assertRaises(util.Needs) as e,
        ):
            install.install(cfg(), '/etc/agentlab/cluster.toml')
        self.assertEqual(ran, [])
        self.assertIn('unsupported host', str(e.exception))


if __name__ == '__main__':
    unittest.main()
