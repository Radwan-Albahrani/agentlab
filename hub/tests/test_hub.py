"""Hub backend tests; run from hub/: python3 -m unittest discover -s tests"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = tempfile.mkdtemp(prefix='hub-test-')
sys.path[:0] = [os.path.dirname(HERE), HERE]
import fake_agent  # noqa: E402
import fixtures  # noqa: E402

fixtures.main(ROOT)
AGENTS = ThreadingHTTPServer(('127.0.0.1', 0), fake_agent.Handler)
threading.Thread(target=AGENTS.serve_forever, daemon=True).start()
os.environ.update(
    HUB_CONFIG=f'{ROOT}/cluster.json',
    HUB_AGENT_URL=f'http://127.0.0.1:{AGENTS.server_port}/{{id}}',
    HUB_ACCESS_CERTS_URL=f'file://{ROOT}/certs-{{team}}.json',
    WATCH_DIR=f'{ROOT}/watch',
    RENDERED_DIR=f'{ROOT}/rendered',
    COMPANIONS_DIR=f'{ROOT}/companions',
    SECRETS_DIR=f'{ROOT}/secrets',
    NOTIFY_DATA=f'{ROOT}/data',
    NOTIFY_T3=f'{ROOT}/agents/{{id}}/home/.t3/userdata',
    AGENTS_DIR=f'{ROOT}/agents',
)
import access  # noqa: E402
import actions  # noqa: E402
import cluster  # noqa: E402
import domains  # noqa: E402
import hub  # noqa: E402
import routes  # noqa: E402
import scope  # noqa: E402
import screens  # noqa: E402
import store  # noqa: E402


def _prime(bits):
    while True:
        n = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if all(pow(a, n - 1, n) == 1 for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)):
            return n


def _key():
    e = 65537
    while True:
        p, q = _prime(512), _prime(512)
        phi = (p - 1) * (q - 1)
        if p != q and phi % e:
            return p * q, e, pow(e, -1, phi)


N, E, D = _key()
SIZE = (N.bit_length() + 7) // 8


def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def token(claims=None, head=None, key=(N, D)):
    head = {'alg': 'RS256', 'kid': 'k1', **(head or {})}
    body = {
        'aud': ['aud-example'],
        'iss': 'https://example.cloudflareaccess.com',
        'exp': time.time() + 600,
        'email': 'admin@example.com',
        **(claims or {}),
    }
    signed = f'{b64(json.dumps(head).encode())}.{b64(json.dumps(body).encode())}'
    t = access.SHA256_PREFIX + hashlib.sha256(signed.encode()).digest()
    em = b'\x00\x01' + b'\xff' * (SIZE - len(t) - 3) + b'\x00' + t
    sig = pow(int.from_bytes(em, 'big'), key[1], key[0]).to_bytes(SIZE, 'big')
    return f'{signed}.{b64(sig)}'


def use_access(mode='cloudflare-access'):
    path = f'{ROOT}/cluster.json'
    conf = json.loads(Path(path).read_text())
    conf['auth'].update(mode=mode, cloudflare={'team': 'example', 'audience': 'aud-example'})
    Path(path).write_text(json.dumps(conf))
    os.utime(path, (time.time() + 1, time.time() + 1))  # a new mtime even within the same second
    cluster.load()


def signed(email='admin@example.com', **claims):
    return {'X-Agentlab-User': email, 'Cf-Access-Jwt-Assertion': token({'email': email, **claims})}


jwks = {'keys': [{'kty': 'RSA', 'kid': 'k1', 'n': b64(N.to_bytes(SIZE, 'big')), 'e': b64(E.to_bytes(3, 'big'))}]}
Path(f'{ROOT}/certs-example.json').write_text(json.dumps(jwks))


class Access(unittest.TestCase):
    def setUp(self):
        use_access()

    def tearDown(self):
        use_access('none')

    def test_admin(self):
        who = access.viewer(signed())
        self.assertEqual((who.email, who.admin, who.agents), ('admin@example.com', True, {'admin'}))

    def test_owner(self):
        who = access.viewer(signed('Sara@example.com'))
        self.assertEqual((who.email, who.admin, who.agents), ('sara@example.com', False, {'sara', 'lab'}))

    def test_cookie(self):
        headers = {'X-Agentlab-User': 'admin@example.com', 'Cookie': f'a=b; CF_Authorization={token()}'}
        self.assertTrue(access.viewer(headers).admin)

    def test_refused(self):
        other = (N + 2, D)

        def tok(claims=None, **kw):
            return {'X-Agentlab-User': 'admin@example.com', 'Cf-Access-Jwt-Assertion': token(claims, **kw)}

        cases = {
            'no headers': {},
            'no user header': {'Cf-Access-Jwt-Assertion': token()},
            'no token': {'X-Agentlab-User': 'admin@example.com'},
            'header and token disagree': {
                'X-Agentlab-User': 'admin@example.com',
                'Cf-Access-Jwt-Assertion': token({'email': 'sara@example.com'}),
            },
            'nobody with an agent': signed('stranger@example.com'),
            'wrong audience': tok({'aud': ['other']}),
            'wrong issuer': tok({'iss': 'https://evil.cloudflareaccess.com'}),
            'expired': tok({'exp': time.time() - 3600}),
            'not yet': tok({'nbf': time.time() + 3600}),
            'alg none': tok(head={'alg': 'none'}),
            'unknown key': tok(head={'kid': 'k9'}),
            'forged': tok(key=other),
            'tampered': {'X-Agentlab-User': 'admin@example.com', 'Cf-Access-Jwt-Assertion': token()[:-6] + 'AAAAAA'},
            'garbage': {'X-Agentlab-User': 'admin@example.com', 'Cf-Access-Jwt-Assertion': 'a.b'},
        }
        for why, headers in cases.items():
            with self.subTest(why), self.assertRaises(access.DeniedError):
                access.viewer(headers)

    def test_https_takes_the_gates_proof_instead_of_a_token(self):
        path = f'{ROOT}/cluster.json'
        conf = json.loads(Path(path).read_text())
        conf['auth']['cloudflare']['https'] = True
        Path(path).write_text(json.dumps(conf))
        os.utime(path, (time.time() + 2, time.time() + 2))
        cluster.load()
        key = Path(f'{ROOT}/gate-session.key')
        key.write_text('ab' * 32)
        sub = hmac.new(bytes.fromhex('ab' * 32), b'agentlab proof v1', hashlib.sha256).digest()

        def proved(user='sara@example.com', admin='0', agent='sara', exp=None, mac_user=None):
            exp = int(time.time()) + 60 if exp is None else exp
            msg = f'{mac_user or user}\n{admin}\n{agent}\n{exp}'.encode()
            mac = base64.urlsafe_b64encode(hmac.new(sub, msg, hashlib.sha256).digest()).rstrip(b'=').decode()
            return {
                'X-Agentlab-User': user,
                'X-Agentlab-Admin': admin,
                'X-Agentlab-Agent': agent,
                'X-Agentlab-Proof': f'{exp}.{mac}',
            }

        with mock.patch.object(access, 'GATE_KEY', str(key)):
            self.assertEqual(access.viewer(proved()).email, 'sara@example.com')
            self.assertTrue(access.viewer(signed()).admin)
            for why, headers in {
                'someone else': proved('admin@example.com', mac_user='sara@example.com'),
                'expired': proved(exp=int(time.time()) - 1),
                'tampered': {**proved(), 'X-Agentlab-Agent': 'lab'},
                'no proof': {'X-Agentlab-User': 'sara@example.com'},
            }.items():
                with self.subTest(why), self.assertRaises(access.DeniedError):
                    access.viewer(headers)
        with mock.patch.object(access, 'GATE_KEY', f'{ROOT}/missing.key'), self.assertRaises(access.DeniedError):
            access.viewer(proved())

    def test_published_port_one_owner(self):
        os.environ['HUB_PUBLISHED_OWNER'] = 'Sara@example.com'
        try:
            who = access.viewer({})
            self.assertEqual((who.email, who.admin, who.agents), ('sara@example.com', True, {'sara', 'lab'}))
            with self.assertRaises(access.DeniedError):
                access.viewer({'X-Agentlab-User': 'sara@example.com'})
        finally:
            del os.environ['HUB_PUBLISHED_OWNER']
        with self.assertRaises(access.DeniedError):
            access.viewer({})

    def test_none_needs_the_switch(self):
        use_access('none')
        os.environ.pop('HUB_ALLOW_NONE', None)
        with self.assertRaises(access.DeniedError):
            access.viewer({})
        os.environ['HUB_ALLOW_NONE'] = '1'
        self.assertTrue(access.viewer({}).admin)
        self.assertEqual(access.viewer({'X-Agentlab-User': 'sara@example.com'}).agents, {'sara', 'lab'})

    def test_http(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), hub.Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{server.server_port}'

        def status(path, headers=None):
            try:
                with urllib.request.urlopen(urllib.request.Request(base + path, headers=headers or {})) as r:
                    return r.status, json.loads(r.read()) if path.startswith('/api/') else None
            except urllib.error.HTTPError as e:
                e.close()
                return e.code, None

        try:
            self.assertEqual(status('/health')[0], 200)
            for path in ('/api/nav', '/', '/agents'):
                with self.subTest(path):
                    self.assertEqual(status(path)[0], 403)
            code, nav = status('/api/nav', signed())
            self.assertEqual((code, [a['name'] for a in nav['agents']]), (200, ['admin', 'sara', 'lab']))
            code, nav = status('/api/nav', signed('sara@example.com'))
            self.assertEqual((code, [a['name'] for a in nav['agents']]), (200, ['sara', 'lab']))
            for path in ('/api/agents/admin', '/api/companions/scout', '/api/services', '/api/secrets'):
                with self.subTest(path):
                    self.assertEqual(status(path, signed('sara@example.com'))[0], 403)
        finally:
            server.shutdown()
            server.server_close()


def as_person(email):
    scope.use(scope.of(email))


class Scope(unittest.TestCase):
    def tearDown(self):
        scope.use(scope.ADMIN)

    def test_screens_leave_others_out(self):
        as_person('sara@example.com')
        nav = screens.nav()
        self.assertEqual([a['name'] for a in nav['agents']], ['sara', 'lab'])
        self.assertEqual([c['name'] for c in nav['agents'][0]['companions']], ['helper'])
        self.assertEqual([s['key'] for s in nav['system']], ['storage'])
        self.assertEqual(nav['colors'], {'sara': 'green'})
        self.assertEqual([a['name'] for a in screens.agents('')['agents']], ['sara', 'lab'])
        seen = json.dumps([screens.overview(), screens.storage(), nav])
        for other in ('scout', 'Scout', 'agent-admin', 'agentlab-core', 'admin@example.com', '"admin"'):
            self.assertNotIn(other, seen)
        storage = screens.storage()
        self.assertEqual(
            [(p['email'], p['agents']) for p in storage['people']], [('sara@example.com', ['sara', 'lab'])]
        )
        self.assertFalse(storage['manage'])
        self.assertEqual(screens.overview()['tiles']['diskLabel'], 'Your disk')

    def test_routes_refuse_others(self):
        as_person('sara@example.com')
        for table, path in (
            (routes.GET, '/api/agents/admin'),
            (routes.GET, '/api/agents/admin/accounts'),
            (routes.GET, '/api/agents/admin/onboarding'),
            (routes.GET, '/api/agents/admin/devices'),
            (routes.GET, '/api/companions/scout'),
            (routes.GET, '/api/companions/scout/secrets'),
            (routes.GET, '/api/companions/scout/secrets/value'),
            (routes.GET, '/api/companions/scout/logs'),
            (routes.GET, '/api/services'),
            (routes.GET, '/api/secrets'),
            (routes.GET, '/api/secrets/value'),
            (routes.GET, '/api/configs'),
            (routes.GET, '/api/notifications'),
            (routes.GET, '/api/display'),
            (routes.POST, '/api/agents/admin/accounts/act'),
            (routes.POST, '/api/agents/admin/pair'),
            (routes.POST, '/api/agents/admin/onboarding/finish'),
            (routes.POST, '/api/agents/admin/devices/revoke'),
            (routes.POST, '/api/companions/scout/restart'),
            (routes.POST, '/api/companions/scout/remove'),
            (routes.POST, '/api/companions/scout/secret'),
            (routes.POST, '/api/companions/scout/review'),
            (routes.POST, '/api/secrets/save'),
            (routes.POST, '/api/config/deploy'),
            (routes.POST, '/api/display/presenting'),
            (routes.POST, '/api/storage/cleanup'),
        ):
            with self.subTest(path), self.assertRaises(routes.ForbiddenError):
                routes.resolve(table, path)

    def test_extra_secrets_are_their_own_group_for_admins_only(self):
        sec = store.secrets
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'jellyfin-api-key.txt').write_text('k1')
            Path(d, 'map.json').write_text(json.dumps({'jellyfin-api-key.txt': {'label': 'Jellyfin API key'}}))
            with (
                mock.patch.object(sec, 'EXTRA', d),
                mock.patch.object(sec, 'EXTRA_MAP', f'{d}/map.json'),
                mock.patch.object(sec, 'EXTRA_LABEL', 'Homelab'),
            ):
                scope.use(scope.ADMIN)
                items = {s['name']: s for s in screens.secrets()['items']}
                extra = items['extra/jellyfin-api-key.txt']
                self.assertEqual((extra['group'], extra['label']), ('Homelab', 'Jellyfin API key'))
                self.assertEqual(items['extra/map.json']['group'], 'Homelab')
                self.assertTrue(sec.save('extra/jellyfin-api-key.txt', 'k2'))
                self.assertEqual(Path(d, 'jellyfin-api-key.txt').read_text(), 'k2')
                self.assertEqual(len(sec.secret_versions('extra/jellyfin-api-key.txt')), 1)
                with self.assertRaises(ValueError):
                    sec.save('extra/../jellyfin-api-key.txt', 'x')
                as_person('sara@example.com')
                for table, path in ((routes.GET, '/api/secrets'), (routes.POST, '/api/secrets/save')):
                    with self.subTest(path), self.assertRaises(routes.ForbiddenError):
                        routes.resolve(table, path)
                with self.assertRaises((ValueError, routes.ForbiddenError)):
                    actions.companion('helper', 'secret', {'file': '../../extra/jellyfin-api-key.txt', 'value': 'x'})

    def test_own_things_work(self):
        as_person('sara@example.com')
        for path in (
            '/api/agents/sara',
            '/api/agents/lab',
            '/api/agents/sara/accounts',
            '/api/agents/lab/onboarding',
            '/api/storage',
            '/api/agents/sara/devices',
            '/api/companions/helper',
            '/api/companions/helper/secrets',
        ):
            with self.subTest(path):
                handler, groups = routes.resolve(routes.GET, path)
                json.dumps(handler(groups, {}, ''))
        files = {s['file']: s['set'] for s in screens.companion_secrets('helper')['items']}
        self.assertTrue(files['owner.txt'])
        self.assertFalse(files['bot-token.txt'])

    def test_onboarding_and_pairing(self):
        as_person('sara@example.com')

        def post(path, body):
            handler, groups = routes.resolve(routes.POST, path)
            return handler(groups, body, '')

        handler, groups = routes.resolve(routes.GET, '/api/agents/sara/onboarding')
        self.assertFalse(handler(groups, {}, '')['done'])
        self.assertEqual(post('/api/agents/sara/onboarding/finish', {}), 'All set.')
        self.assertTrue(handler(groups, {}, '')['done'])
        link = post('/api/agents/sara/pair', {'kind': 'browser', 'label': 'x', 'evil': 1})
        self.assertTrue(link['url'].startswith('https://agents.example.com/pair#token='))
        self.assertFalse(post('/api/agents/sara/pair', {'kind': 'app', 'label': 'iPhone'})['available'])
        cluster.use_host('homebox:7190')
        try:
            post('/api/agents/sara/pair', {'kind': 'browser', 'label': 'x', 'host': 'evil.com'})
        finally:
            cluster.use_host('')
        self.assertEqual(fake_agent.PAIR_BODIES[-1], {'kind': 'browser', 'label': 'x', 'host': 'homebox'})

    def test_companion_secret_and_logs(self):
        as_person('admin@example.com')
        self.assertIn('connected to Slack', screens.companion_logs('scout')['text'])
        actions.companion('scout', 'secret', {'file': 'app-token.txt', 'value': 'xapp-example'})
        self.assertEqual(store.secrets.value('companions/scout/app-token.txt'), 'xapp-example')
        with self.assertRaises(ValueError):
            actions.companion('scout', 'secret', {'file': '../../coolify.token', 'value': 'x'})
        with self.assertRaises(ValueError):
            actions.companion('scout', 'secret', {'file': 'random.txt', 'value': 'x'})


class Screens(unittest.TestCase):
    def setUp(self):
        os.environ['HUB_ALLOW_NONE'] = '1'

    def test_every_screen_renders(self):
        for name, render in {
            'nav': screens.nav,
            'overview': screens.overview,
            'agents': lambda: screens.agents(''),
            'agent': lambda: screens.agent('', 'sara'),
            'companion': lambda: screens.companion('scout'),
            'services': screens.services,
            'configs': screens.configs,
            'config': lambda: screens.config('agentlab-core'),
            'storage': screens.storage,
            'manage': screens.manage,
            'secrets': screens.secrets,
            'notifications': screens.notifications,
            'display': screens.display_settings,
        }.items():
            with self.subTest(name):
                json.dumps(render(), default=str)

    def test_agents_come_from_the_config(self):
        nav = screens.nav()
        self.assertEqual([a['name'] for a in nav['agents']], ['admin', 'sara', 'lab'])
        self.assertEqual(nav['agents'][0]['companions'][0]['name'], 'scout')

    def test_links_go_through_the_view_switch(self):
        card = screens.agents('')['agents'][0]
        self.assertEqual(card['links']['chat'], 'https://agents.example.com/_agentlab/view/admin?next=/')
        self.assertEqual(
            card['links']['files'], 'https://agents.example.com/_agentlab/view/admin?next=/_agentlab/files/'
        )
        self.assertIn('/_agentlab/view/admin?next=/_agentlab/accounts/browser', card['links']['browser'])
        self.assertIsNone(screens.agents('')['agents'][1]['links']['browser'])

    def test_published_tools_link_straight_to_their_ports(self):
        ports = {'t3': 7101, 'terminal': 7104, 'files': 7105, 'browser': 7103}
        with mock.patch.object(cluster, 'published', lambda agent_id: ports if agent_id == 'admin' else {}):
            cluster.use_host('HomeBox.tail.ts.net:7190')
            try:
                links = cluster.links('admin')
                other = cluster.links('sara')
            finally:
                cluster.use_host('')
        self.assertEqual(links['chat'], 'http://homebox.tail.ts.net:7101/')
        self.assertEqual(links['terminal'], 'http://homebox.tail.ts.net:7104/_agentlab/terminal/')
        self.assertEqual(links['files'], 'http://homebox.tail.ts.net:7105/_agentlab/files/')
        self.assertTrue(links['browser'].startswith('http://homebox.tail.ts.net:7103/vnc.html'))
        self.assertEqual(links['accounts'], '/agents/admin/accounts')
        self.assertTrue(other['chat'].startswith('https://agents.example.com/_agentlab/view/sara'))
        for odd in ('[::1]:7190', 'a b', 'x/y'):
            cluster.use_host(odd)
            self.assertEqual(cluster.request_host(), '')
        cluster.use_host('')

    def test_stacks_group_by_agent(self):
        self.assertEqual(domains.domain_of('agentlab-agent-sara'), ('sara', 'agent'))
        self.assertEqual(domains.domain_of('agentlab-companion-scout'), ('admin', 'scout'))
        self.assertEqual(domains.domain_of('agentlab-agent-nobody'), (None, None))
        services = screens.services()
        self.assertEqual([d['profile'] for d in services['domains']], ['admin', 'sara', 'lab'])
        self.assertEqual([s['id'] for s in services['other']], ['agentlab-core', 'media'])
        self.assertIn('media-jellyfin-1', store.watch.container_names())
        self.assertNotIn('stray-1', store.watch.container_names())
        self.assertNotIn('media', [s['id'] for s in store.stacks.stacks()])

    def test_storage_per_person_disk(self):
        people = {p['email']: p for p in screens.storage()['people']}
        self.assertEqual(people['sara@example.com']['used'], 50 * fixtures.GB)
        self.assertEqual(people['sara@example.com']['agents'], ['sara', 'lab'])
        titles = [n['title'] for n in screens.overview()['needs']]
        self.assertIn("sara@example.com's disk 83% full", titles)

    def test_secrets_map_spells_out_companions(self):
        items = {s['name']: s for s in screens.secrets()['items']}
        token = items['companions/scout/bot-token.txt']
        self.assertEqual(token['label'], 'Scout · Slack bot token')
        self.assertEqual(token['effect'], 'On change: restarts companion-scout.')
        self.assertEqual(items['unmapped-note.txt']['kinds'], ['unmapped'])

    def test_secret_names_stay_in_their_folders(self):
        self.assertEqual(store.secrets.value('companions/scout/owner.txt'), 'U0EXAMPLE\n')
        for name in (
            '../cluster.json',
            'companions/nobody/owner.txt',
            'companions/scout/../../x',
            '.versions/x',
            'a/b',
        ):
            with self.subTest(name), self.assertRaises(ValueError):
                store.secrets.value(name)

    def test_companion_not_set_up(self):
        c = screens.companion('helper')
        self.assertEqual(c['state'], 'unconfigured')
        needs = {n['title']: n['tone'] for n in screens.overview()['needs']}
        self.assertEqual(needs['Helper is not set up yet'], 'info')

    def test_template_update_state_comes_from_agentctl(self):
        t = screens.companion('scout')['templateUpdate']
        self.assertEqual((t['state'], t['from'], t['to']), ('conflict', 'a1b2c3d', 'e4f5a6b'))
        self.assertIn('bot/prompts.py', t['detail'])
        self.assertEqual(screens.companion('helper')['templateUpdate'], {})

    def test_pulls_and_polls(self):
        c = screens.companion('scout')
        self.assertEqual(c['pulls']['items'][0]['id'], 'example/app#12')
        self.assertEqual(c['pulls']['me'], 'example-admin')
        self.assertEqual(c['polls'][0]['question'], 'Lunch on Thursday?')

    def test_people_setting_offers_the_workspace_and_takes_ids(self):
        field = next(f for f in screens.companion('scout')['settings'] if f['key'] == 'access')
        self.assertEqual(field['options'][0], {'value': 'U0ALI', 'label': 'Ali', 'avatar': ''})
        self.assertEqual(field['when'], {'mode': ['review']})
        store.companions.set_setting('scout', 'access', ['U0ALI', 'U0ALI'])
        self.assertEqual(store.companions.settings('scout')[2][1], ['U0ALI'])
        with self.assertRaises(ValueError):
            store.companions.set_setting('scout', 'access', 'U0ALI')
        store.companions.set_setting('scout', 'access', [])


class Routes(unittest.TestCase):
    def test_unknown_agent_or_companion_is_404(self):
        for path in ('/api/agents/nobody', '/api/agents/nobody/accounts', '/api/companions/nobody'):
            with self.subTest(path), self.assertRaises(routes.NotFoundError):
                routes.resolve(routes.GET, path)

    def test_accounts_page_from_the_agent(self):
        handler, groups = routes.resolve(routes.GET, '/api/agents/admin/accounts')
        page = handler(groups, {}, '')
        self.assertEqual(page['agent'], 'admin')
        self.assertTrue(page['browserUrl'].startswith('https://agents.example.com/_agentlab/view/admin'))

    def test_deploy_is_a_watcher_request(self):
        self.assertIn('Deploying', actions.config_deploy({'id': 'agentlab-agent-sara'}))
        self.assertTrue(os.path.exists(f'{ROOT}/watch/requests/deploy~agentlab-agent-sara'))
        with self.assertRaises(ValueError):
            actions.config_deploy({'id': '../etc'})

    def test_companion_remove_is_a_watcher_request(self):
        actions.companion('scout', 'remove', {})
        self.assertTrue(os.path.exists(f'{ROOT}/watch/requests/remove~companion~scout'))

    def test_companion_restart_finds_its_container(self):
        actions.companion('scout', 'restart', {})
        self.assertTrue(os.path.exists(f'{ROOT}/watch/requests/restart~companion-scout'))

    def test_manage_queues_checked_jobs_for_the_watcher(self):
        queue = f'{ROOT}/watch/jobs/queue'
        self.assertIn('Adding lina', actions.manage('add', {'id': 'lina', 'email': 'Lina@Example.com', 'memory': '8g'}))
        jobs = [json.loads(Path(queue, n).read_text()) for n in sorted(os.listdir(queue))]
        self.assertEqual(jobs[-1]['op'], 'agent.add')
        self.assertEqual(jobs[-1]['args'], {'id': 'lina', 'email': 'lina@example.com', 'memory': '8g'})
        self.assertEqual(store.jobs.recent()[0]['state'], 'queued')
        for what, body in (
            ('add', {'id': 'sara', 'email': 'x@example.com'}),  # taken
            ('add', {'id': 'Bad Name', 'email': 'x@example.com'}),
            ('add', {'id': 'ok', 'email': 'nope'}),
            ('resize', {'id': 'sara', 'memory': 'lots'}),
            ('resize', {'id': 'nobody', 'memory': '8g'}),
            ('remove', {'id': 'sara', 'deleteData': True, 'confirm': 'wrong'}),
            ('remove', {'id': 'admin'}),  # has a companion
        ):
            with self.subTest(what=what, body=body), self.assertRaises(ValueError):
                actions.manage(what, body)
        actions.manage('remove', {'id': 'lab', 'deleteData': True, 'confirm': 'lab'})
        self.assertIn('Resizing disks', actions.disk_sizes({'personSize': 'auto', 'hostReserve': '64g'}))
        with self.assertRaises(ValueError):
            actions.disk_sizes({'personSize': 'huge'})

    def test_a_published_setup_adds_agents_for_its_one_person(self):
        published = {
            **cluster.load(),
            'agents': [{**a, 'owner': 'admin@example.com', 'publish': {'t3': 7101}} for a in cluster.load()['agents']],
        }
        with mock.patch.object(cluster, 'load', return_value=published):
            self.assertEqual(screens.access_setup(published)['fixedOwner'], 'admin@example.com')
            with self.assertRaises(ValueError):
                actions.manage('add', {'id': 'other', 'email': 'someone@example.com'})
            actions.manage('add', {'id': 'research'})
        queue = f'{ROOT}/watch/jobs/queue'
        newest = max(sorted(os.listdir(queue)), key=lambda n: Path(queue, n).stat().st_mtime)
        self.assertEqual(json.loads(Path(queue, newest).read_text())['args']['email'], 'admin@example.com')
        self.assertEqual(screens.access_setup(cluster.load())['fixedOwner'], '')

    def test_manage_is_admin_only(self):
        scope.use(scope.Viewer('sara@example.com', False, frozenset({'sara', 'lab'})))
        try:
            with self.assertRaises(routes.ForbiddenError):
                routes.resolve(routes.GET, '/api/manage')
            with self.assertRaises(routes.ForbiddenError):
                routes.resolve(routes.POST, '/api/manage/add')
        finally:
            scope.use(scope.ADMIN)

    def test_stacks_are_read_only(self):
        self.assertEqual(store.stacks.stacks()[0]['id'], 'agentlab-agent-admin')
        with self.assertRaises(ValueError):
            store.stacks.read('../../cluster.json')


if __name__ == '__main__':
    unittest.main()
