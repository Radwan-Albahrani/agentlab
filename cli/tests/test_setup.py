import contextlib
import io
import os
import re
import stat
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentlab import cloudflare, config, secret, setup, util

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MACHINE = {'name': 'box', 'tailnet': '', 'kvm': False, 'wsl': False}


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


def resolve(text, data):
    return config.resolve(tomllib.loads(text.replace('[cluster]\n', f'[cluster]\ndata = "{data}"\n', 1)))


class Answers(unittest.TestCase):
    def ask(self, flags, interactive=False, replies=(), machine=MACHINE):
        replies = list(replies)
        asker = setup.Asker(flags, interactive, lambda _q: replies.pop(0) if replies else '')
        with quiet():
            return setup.answers(flags, asker, machine), asker.missing

    def test_people_and_their_agent_ids(self):
        people = setup.parse_people('sara@example.com=2, Omar@Example.com')
        self.assertEqual(people, [('sara@example.com', 2), ('omar@example.com', 1)])
        self.assertEqual([i for _, i in setup.agent_ids(people)], ['sara', 'sara-2', 'omar'])
        self.assertEqual(setup.agent_ids([('9x@example.com', 1)])[0][1], 'a-9x')
        with self.assertRaises(util.Failed):
            setup.parse_people('not-an-email')

    def test_just_me_needs_only_an_email(self):
        a, missing = self.ask({'admin': 'me@example.com'})
        self.assertEqual(missing, [])
        self.assertEqual((a['reach'], a['domain'], [i for _, i in a['agents']]), ('me', 'box', ['main']))
        cfg = resolve(setup.toml_text(a), tempfile.gettempdir())
        self.assertEqual(cfg['auth']['mode'], 'none')
        self.assertEqual(
            cfg['agents'][0]['publish'],
            {'t3': 7101, 'accounts': 7102, 'browser': 7103, 'terminal': 7104, 'files': 7105},
        )
        self.assertEqual(cfg['hub']['publish'], 7190)
        self.assertTrue(config.ports_only(cfg))

    def test_just_me_on_a_tailnet_uses_its_name(self):
        machine = {**MACHINE, 'tailnet': 'box.tail1234.ts.net'}
        a, _ = self.ask({'admin': 'me@example.com', 'agents': 'work, personal'}, machine=machine)
        cfg = resolve(setup.toml_text(a), tempfile.gettempdir())
        self.assertEqual((cfg['auth']['mode'], cfg['domain']), ('tailscale', 'box'))
        self.assertEqual([a['publish']['t3'] for a in cfg['agents']], [7101, 7111])

    def test_shared_setups_say_what_is_missing(self):
        _, missing = self.ask({'reach': 'cloudflare'})
        self.assertEqual(missing, ['--admin', '--domain', '--people'])

    def test_cloudflare_answers_make_a_valid_config(self):
        a, missing = self.ask(
            {
                'reach': 'cloudflare',
                'admin': 'boss@example.com',
                'domain': 'agents.example.com',
                'people': 'boss@example.com, sara@example.com=2',
                'allow_domains': 'example.com',
            }
        )
        self.assertEqual(missing, [])
        cfg = resolve(setup.toml_text(a), tempfile.gettempdir())
        self.assertEqual(cfg['auth']['mode'], 'cloudflare-access')
        self.assertEqual(cfg['hub_domain'], 'agents-hub.example.com')
        self.assertEqual(cfg['storage']['mode'], 'per-person')
        self.assertEqual([x['id'] for x in cfg['agents']], ['boss', 'sara', 'sara-2'])
        self.assertEqual(cfg['auth']['allow_domains'], ['example.com'])
        self.assertEqual(cfg['deploy'], 'compose')

    def test_tinyauth_and_tailnet_configs_are_valid(self):
        a, _ = self.ask({'reach': 'tinyauth', 'admin': 'b@example.com', 'domain': 'agents.example.com'})
        cfg = resolve(setup.toml_text(a), tempfile.gettempdir())
        self.assertEqual(cfg['tinyauth']['domain'], 'agents-auth.example.com')
        a, _ = self.ask(
            {'reach': 'tailnet', 'admin': 'b@example.com', 'people': 'b@example.com, c@example.com'},
            machine={**MACHINE, 'tailnet': 'box.tail1234.ts.net'},
        )
        cfg = resolve(setup.toml_text(a), tempfile.gettempdir())
        self.assertEqual((cfg['domain'], cfg['auth']['mode']), ('box.tail1234.ts.net', 'tailscale'))

    def test_questions_at_a_terminal(self):
        replies = [
            '3',
            'boss@example.com',
            'agents.example.com',
            '',
            '',
            '',
            'boss@example.com=1, sara@example.com',
            '',
        ]
        a, missing = self.ask({}, interactive=True, replies=replies)
        self.assertEqual(missing, [])
        self.assertEqual(
            (a['reach'], a['domain'], a['hub_domain']), ('cloudflare', 'agents.example.com', 'agents-hub.example.com')
        )
        self.assertEqual([i for _, i in a['agents']], ['boss', 'sara'])
        self.assertEqual(a['network'], 'private')

    def test_a_bad_reply_is_asked_again(self):
        replies = ['1', 'nope', 'me@example.com', '', '']
        a, _ = self.ask({}, interactive=True, replies=replies)
        self.assertEqual(a['admin'], 'me@example.com')

    def test_android_only_where_kvm_is(self):
        a, _ = self.ask({'admin': 'me@example.com'}, machine={**MACHINE, 'kvm': True})
        self.assertTrue(a['android'])
        a, _ = self.ask({'admin': 'me@example.com'})
        self.assertFalse(a['android'])
        a, _ = self.ask({'admin': 'me@example.com'}, machine={**MACHINE, 'wsl': True})
        self.assertEqual(a['isolation'], 'unconfined')


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = f'{self.tmp.name}/cluster.toml'
        self.ran = []
        self.steps = {
            'init': lambda: self.ran.append('init'),
            'install': lambda cfg: self.ran.append('install'),
            'cloudflare': lambda cfg: self.ran.append('cloudflare'),
            'apply': lambda cfg: self.ran.append('apply'),
        }
        data = self.tmp.name
        self.enterContext(mock.patch.object(setup, 'facts', return_value=MACHINE))
        real = setup.toml_text
        self.enterContext(
            mock.patch.object(
                setup,
                'toml_text',
                side_effect=lambda a: real(a).replace('[cluster]\n', f'[cluster]\ndata = "{data}"\n', 1),
            )
        )

    def run_setup(self, flags, interactive=False, replies=()):
        replies = list(replies)
        with quiet():
            return setup.setup(self.path, flags, lambda _q: replies.pop(0) if replies else '', interactive, self.steps)

    def test_just_me_runs_everything_in_order(self):
        result = self.run_setup({'admin': 'me@example.com'})
        self.assertEqual(self.ran, ['init', 'install', 'apply'])
        self.assertEqual(result['open']['hub'], 'http://box:7190')
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode) & 0o077, 0o040)

    def test_cloudflare_stops_for_the_token_then_carries_on(self):
        flags = {'reach': 'cloudflare', 'admin': 'b@example.com', 'domain': 'agents.example.com'}
        with self.assertRaisesRegex(util.Needs, 'agentctl secret set cloudflare-api'):
            self.run_setup(flags)
        self.assertEqual(self.ran, ['init'])
        os.makedirs(f'{self.tmp.name}/secrets', exist_ok=True)
        with open(f'{self.tmp.name}/secrets/cloudflare-api.token', 'w') as f:
            f.write('t')
        self.ran.clear()
        self.run_setup({})
        self.assertEqual(self.ran, ['init', 'install', 'cloudflare', 'apply'])

    def test_missing_answers_without_a_terminal(self):
        with self.assertRaisesRegex(util.Needs, '--admin'):
            self.run_setup({'reach': 'tailnet'})
        self.assertFalse(os.path.exists(self.path))

    def test_an_existing_config_is_replaced_only_with_yes(self):
        self.run_setup({'admin': 'me@example.com'})
        with open(self.path) as f:
            first = f.read()
        with self.assertRaisesRegex(util.Needs, '--yes'):
            self.run_setup({'admin': 'me@example.com', 'agents': 'work, play'})
        self.run_setup({'admin': 'me@example.com', 'agents': 'work, play', 'yes': True})
        with open(self.path + '.before-setup') as f:
            self.assertEqual(f.read(), first)
        with open(self.path) as f:
            self.assertIn('id = "play"', f.read())

    def test_rerunning_with_the_same_answers_changes_nothing(self):
        self.run_setup({'admin': 'me@example.com'})
        mtime = os.stat(self.path).st_mtime_ns
        self.run_setup({'admin': 'me@example.com'})
        self.assertEqual(os.stat(self.path).st_mtime_ns, mtime)

    def test_a_step_that_needs_a_person_waits_at_a_terminal(self):
        tries = []

        def install(cfg):
            tries.append(1)
            if len(tries) == 1:
                raise util.Needs('open https://login.tailscale.com/a/x to sign in')
            self.ran.append('install')

        self.steps['install'] = install
        self.run_setup({'admin': 'me@example.com'}, interactive=True, replies=['', '', '', '', ''])
        self.assertEqual(len(tries), 2)
        self.assertIn('apply', self.ran)

    def test_config_only(self):
        self.run_setup({'admin': 'me@example.com', 'config_only': True})
        self.assertEqual(self.ran, [])
        self.assertTrue(os.path.exists(self.path))


class Secrets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        text = f"""[cluster]
name = "t"
domain = "agents.example.com"
hub_domain = "agents-hub.example.com"
data = "{self.tmp.name}"
[auth]
admins = ["b@example.com"]
[[agents]]
id = "b"
owner = "b@example.com"
[[companions]]
name = "helper"
agent = "b"
"""
        self.cfg = config.resolve(tomllib.loads(text))
        self.enterContext(mock.patch.object(secret, 'need_root'))
        self.enterContext(mock.patch('agentlab.secret.os.chown'))

    def put(self, name, value):
        util.OUT.messages.clear()
        with quiet():
            return secret.set_secret(self.cfg, name, io.StringIO(value))

    def test_saved_root_only_where_agentlab_reads_it(self):
        result = self.put('cloudflare-api', 'value-42\n')
        self.assertEqual(result['path'], f'{self.tmp.name}/secrets/cloudflare-api.token')
        with open(result['path']) as f:
            self.assertEqual(f.read(), 'value-42\n')
        self.assertEqual(stat.S_IMODE(os.stat(result['path']).st_mode), 0o600)
        self.assertNotIn('value-42', ''.join(util.OUT.messages))

    def test_companion_secrets_and_unknown_names(self):
        path = self.put('companion/helper/bot-token.txt', 'xoxb-example')['path']
        self.assertEqual(path, f'{self.tmp.name}/secrets/companions/helper/bot-token.txt')
        with self.assertRaisesRegex(util.Failed, 'not a companion secret'):
            self.put('companion/helper/password.txt', 'x')
        with self.assertRaisesRegex(util.Failed, "no companion 'other'"):
            self.put('companion/other/bot-token.txt', 'x')
        with self.assertRaisesRegex(util.Failed, 'unknown secret'):
            self.put('github', 'x')
        with self.assertRaisesRegex(util.Failed, 'no value'):
            self.put('coolify', '\n')

    def test_listing_says_what_is_saved(self):
        self.put('coolify', 'c')
        rows = {r['name']: r['set'] for r in secret.listing(self.cfg)}
        self.assertTrue(rows['coolify'])
        self.assertFalse(rows['cloudflare-api'])

    def test_companion_keys_match_the_watcher(self):
        with open(os.path.join(REPO, 'host', 'watch', 'agent_requests.py')) as f:
            block = re.search(r'SECRET_KEYS = \{(.*?)\}', f.read(), re.S).group(1)
        self.assertEqual(set(re.findall(r"'([^']+)'", block)), set(secret.COMPANION_KEYS))


class FakeAccount:
    def __init__(self, idps=None, org_status=0):
        self.calls = []
        self.idps = idps if idps is not None else [{'id': 'o1', 'name': 'One-time PIN'}]
        self.org_status = org_status  # HTTP status the organization read fails with (0 = it works)

    def call(self, method, path, body=None):
        self.calls.append((method, path))
        if path.endswith('/access/organizations') and self.org_status:
            raise cloudflare.ApiError(f'Cloudflare GET {path}: HTTP {self.org_status}', self.org_status)
        if path == '/zones?name=example.com':
            return [{'id': 'z1', 'name': 'example.com', 'account': {'id': 'acc1'}}]
        if path.startswith('/zones?name='):
            return []
        if path == '/accounts':
            return [{'id': 'acc1'}]
        if path.endswith('/access/organizations'):
            return {'auth_domain': 'acme.cloudflareaccess.com'}
        if path.endswith('/identity_providers'):
            return self.idps
        raise AssertionError(path)


class Discover(unittest.TestCase):
    def cfg(self, extra=''):
        text = f"""[cluster]
name = "t"
domain = "agents.example.com"
hub_domain = "agents-hub.example.com"
data = "{tempfile.gettempdir()}"
[auth]
admins = ["b@example.com"]
{extra}
[[agents]]
id = "b"
owner = "b@example.com"
"""
        return config.resolve(tomllib.loads(text))

    def test_only_the_token_is_needed(self):
        cfg = self.cfg()
        cloudflare.discover(cfg, FakeAccount())
        self.assertEqual((cfg['cloudflare']['zone'], cfg['cloudflare']['account_id']), ('example.com', 'acc1'))
        self.assertEqual(cfg['auth']['cloudflare']['team'], 'acme')

    def test_a_token_that_cant_read_the_organization_asks_for_the_permission_or_the_team(self):
        cfg = self.cfg()
        with self.assertRaises(util.Needs) as e:
            cloudflare.discover(cfg, FakeAccount(org_status=403))
        self.assertIn('Access: Organizations → Edit', str(e.exception))
        self.assertIn('[auth.cloudflare] team', str(e.exception))
        self.assertEqual(e.exception.code, util.NEEDS)

    def test_other_organization_errors_stay_errors(self):
        with self.assertRaises(cloudflare.ApiError) as e:
            cloudflare.discover(self.cfg(), FakeAccount(org_status=500))
        self.assertEqual(e.exception.status, 500)

    def test_a_set_team_never_reads_the_organization(self):
        cfg = self.cfg('[auth.cloudflare]\nteam = "acme"')
        api = FakeAccount(org_status=403)
        cloudflare.discover(cfg, api)
        self.assertFalse(any(p.endswith('/access/organizations') for _, p in api.calls))
        self.assertEqual(cfg['cloudflare']['zone'], 'example.com')

    def test_explicit_keys_win(self):
        cfg = self.cfg('[auth.cloudflare]\nteam = "other"\n[cloudflare]\naccount_id = "acc9"\nzone = "example.com"')
        api = FakeAccount()
        cloudflare.discover(cfg, api)
        self.assertEqual((cfg['cloudflare']['account_id'], cfg['auth']['cloudflare']['team']), ('acc9', 'other'))
        self.assertEqual(api.calls, [])

    def test_one_login_method_is_used_straight_away(self):
        cfg = self.cfg()
        self.assertEqual(cloudflare.login_methods(cfg, [{'id': 'g1', 'name': 'Google'}]), ['g1'])
        self.assertEqual(cloudflare.login_methods(cfg, [{'id': 'g1'}, {'id': 'o1'}]), [])

    def test_setup_writes_what_it_found_into_the_config(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = f'{tmp.name}/cluster.toml'
        with open(path, 'w') as f:
            f.write('[cluster]\nname = "t"\n\n[auth]\nadmins = ["b@example.com"]   # me\n')
        cfg = self.cfg()
        cloudflare.discover(cfg, FakeAccount())
        s = cloudflare.Setup(cfg, FakeAccount(), util.Plan(False))
        with quiet():
            s.remember(path, {('cloudflare', 'zone'): 'example.com', ('auth.cloudflare', 'team'): 'acme'})
        with open(path) as f:
            written = tomllib.loads(f.read())
        self.assertEqual(
            (written['cloudflare']['zone'], written['auth']['cloudflare']['team']), ('example.com', 'acme')
        )


if __name__ == '__main__':
    unittest.main()


class FreshCode(unittest.TestCase):
    def run_setup(self, *extra, pull=('aaa', 'aaa')):
        from agentlab import main, update  # noqa: PLC0415 - main pulls in every command

        execv = mock.Mock()
        pulled = mock.Mock(side_effect=pull) if isinstance(pull, Exception) else mock.Mock(return_value=pull)
        with (
            mock.patch.object(update, 'pull', pulled),
            mock.patch.object(main.os, 'execv', execv),
            mock.patch.object(main.privileges, 'elevate'),
            mock.patch.object(setup, 'setup', return_value={}) as run,
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            main.main(['setup', '--reach', 'me', *extra])
        return pulled, execv, run

    def test_new_code_reruns_setup_on_it(self):
        pulled, execv, _ = self.run_setup(pull=('aaa', 'bbb'))
        pulled.assert_called_once_with('main')
        self.assertEqual(execv.call_args.args[1][-1], '--pulled')

    def test_current_code_just_continues(self):
        _, execv, run = self.run_setup()
        execv.assert_not_called()
        run.assert_called_once()

    def test_a_pull_that_cannot_happen_is_only_a_note(self):
        _, execv, run = self.run_setup(pull=util.Failed('/opt/agentlab has local changes'))
        execv.assert_not_called()
        run.assert_called_once()

    def test_no_pull_and_the_rerun_skip_it(self):
        for flag in ('--no-pull', '--pulled'):
            pulled, _, run = self.run_setup(flag)
            pulled.assert_not_called()
            run.assert_called_once()


class TunnelFirst(unittest.TestCase):
    def setUp(self):
        from agentlab import install  # noqa: PLC0415

        self.install = install
        self.tmp = tempfile.mkdtemp()
        self.api = os.path.join(self.tmp, 'cloudflare-api.token')
        self.env = {'AGENTLAB_TUNNEL_TOKEN': os.path.join(self.tmp, 'cloudflare-tunnel.token')}
        self.cfg = {'auth': {'ingress': 'cloudflared'}, 'cloudflare': {'api_token_file': self.api}}

    def run_it(self):
        with mock.patch.object(self.install.cloudflare, 'setup') as cf, contextlib.redirect_stdout(io.StringIO()):
            self.install.tunnel_first(self.cfg, self.env, '/etc/agentlab/cluster.toml')
        return cf

    def test_creates_the_tunnel_when_the_api_token_is_saved(self):
        open(self.api, 'w').close()
        self.run_it().assert_called_once()

    def test_leaves_it_to_the_step_without_an_api_token(self):
        self.run_it().assert_not_called()

    def test_nothing_to_do_when_the_tunnel_exists_or_another_way_in(self):
        open(self.api, 'w').close()
        open(self.env['AGENTLAB_TUNNEL_TOKEN'], 'w').close()
        self.run_it().assert_not_called()
        os.remove(self.env['AGENTLAB_TUNNEL_TOKEN'])
        self.cfg['auth']['ingress'] = 'tailscale'
        self.run_it().assert_not_called()
