import base64
import contextlib
import copy
import io
import json
import os
import re
import stat
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentlab import (
    apply,
    cloudflare,
    config,
    deploy,
    disks,
    doctor,
    gateway,
    hostsfile,
    init,
    install,
    main,
    privileges,
    render,
    tomledit,
    util,
    wslhost,
    yaml,
)


def setUpModule():
    # tests that run apply on a WSL machine must not reach the real Windows task scheduler
    p = mock.patch.object(wslhost, 'is_wsl', return_value=False)
    p.start()
    unittest.addModuleCleanup(p.stop)


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXAMPLE = os.path.join(REPO, 'cluster.example.toml')

BASE = """
[cluster]
name = "test"
domain = "agents.example.com"
hub_domain = "agents-hub.example.com"
data = "/srv/agentlab"
deploy = "compose"

[auth]
mode = "cloudflare-access"
admins = ["boss@example.com"]

[auth.cloudflare]
team = "example"

[[agents]]
id = "sara"
owner = "sara@example.com"

[[agents]]
id = "omar"
owner = "omar@example.com"
"""


# public hostnames behind the sign-in page (pair hosts need it); BASE is the default, private network
PUBLIC = BASE.replace('team = "example"', 'team = "example"\nnetwork = "public"')


def raw(text=BASE, **sections):
    data = tomllib.loads(text)
    for path, value in sections.items():
        section, key = path.split('__')
        data.setdefault(section, {})[key] = value
    return data


def resolve(text=BASE, previous=None, **sections):
    return config.resolve(raw(text, **sections), previous)


def problems(text=BASE, **sections):
    try:
        resolve(text, **sections)
    except util.Failed as e:
        return str(e)
    return ''


class Config(unittest.TestCase):
    def test_example_resolves(self):
        with open(EXAMPLE, 'rb') as f:
            cfg = config.resolve(tomllib.load(f))
        self.assertEqual([a['id'] for a in cfg['agents']], ['admin', 'sara', 'sara-mobile'])
        self.assertEqual(cfg['auth']['ingress'], 'cloudflared')

    def test_machine_names_and_ips_only_where_people_reach_it_inside_their_network(self):
        tailnet = BASE.replace('mode = "cloudflare-access"', 'mode = "tailscale"').replace(
            'domain = "agents.example.com"', 'domain = "my-server"'
        )
        tailnet = tailnet.replace('hub_domain = "agents-hub.example.com"\n', '')
        self.assertEqual(problems(tailnet), '')
        self.assertEqual(problems(tailnet.replace('"my-server"', '"100.64.0.7"')), '')
        self.assertIn(
            'is not a hostname', problems(BASE.replace('domain = "agents.example.com"', 'domain = "my-server"'))
        )
        self.assertIn('is not a hostname', problems(tailnet.replace('"my-server"', '"my_server"')))

    def test_access_guide_examples_resolve(self):
        with open(os.path.join(os.path.dirname(EXAMPLE), 'skills', 'agentlab', 'references', 'access.md')) as f:
            guide = f.read()
        just_you = guide[guide.index('### Just you') :]
        text = (
            just_you.split('```toml\n', 1)[1].split('```', 1)[0].replace('[cluster]\n', '[cluster]\nname = "home"\n', 1)
        )
        cfg = config.resolve(tomllib.loads(text))
        self.assertEqual([a['publish'].get('t3') for a in cfg['agents']], [7101, 7111])

    def test_public_json_has_the_contract_shape_and_no_private_keys(self):
        out = json.loads(config.to_json(resolve()))
        for key in (
            'name',
            'domain',
            'hub_domain',
            'coolify_domain',
            'pair_domain',
            'agents',
            'auth',
            'storage',
            'limits',
            'android',
            'backups',
            'companions',
            'data',
            'deploy',
            'isolation',
            'timezone',
        ):
            self.assertIn(key, out)
        for key in config.PRIVATE:
            self.assertNotIn(key, out)
        self.assertEqual(
            set(out['auth']), {'mode', 'ingress', 'admins', 'allow_domains', 'cloudflare', 'tinyauth', 'hub_port'}
        )
        agent = out['agents'][0]
        self.assertEqual(agent['upstream'], 'http://agent-sara')
        self.assertEqual(agent['path'], '/srv/agentlab/agents/sara')
        self.assertEqual(agent['subnet'], '10.207.1.0/24')

    def test_every_problem_is_listed_at_once(self):
        text = BASE.replace('mode = "cloudflare-access"', 'mode = "magic"').replace('id = "omar"', 'id = "Omar"')
        found = problems(text, cluster__colour='blue')
        self.assertIn('mode must be one of', found)
        self.assertIn("id 'Omar'", found)
        self.assertIn("unknown key 'colour'", found)

    def test_required_and_reserved(self):
        self.assertIn('domain is required', problems(BASE.replace('domain = "agents.example.com"\n', '')))
        self.assertIn("id 'hub'", problems(BASE.replace('id = "omar"', 'id = "hub"')))
        self.assertEqual('', problems(BASE.replace('team = "example"', 'team = ""')))
        self.assertIn('team must be', problems(BASE.replace('team = "example"', 'team = "Not A Team"')))

    def test_ingress_must_suit_the_mode(self):
        self.assertIn('does not work with mode', problems(auth__ingress='public'))
        cfg = resolve(
            BASE.replace('mode = "cloudflare-access"', 'mode = "tinyauth"')
            + """
[auth.tinyauth]
domain = "login.example.com"
google_client_id_file = "/s/id"
google_client_secret_file = "/s/secret"
""",
            auth__ingress='cloudflared',
        )
        self.assertEqual(cfg['auth']['ingress'], 'cloudflared')

    def test_allow_domains(self):
        cfg = resolve(BASE, auth__allow_domains=['Example.com'])
        self.assertEqual(cfg['auth']['allow_domains'], ['example.com'])
        self.assertIn('allow_domains must be a list', problems(auth__allow_domains=['not a domain']))
        self.assertIn(
            'allow_domains works with',
            problems(BASE.replace('mode = "cloudflare-access"', 'mode = "tailscale"'), auth__allow_domains=['x.io']),
        )

    def test_owners_may_own_several_agents(self):
        cfg = resolve(BASE.replace('owner = "omar@example.com"', 'owner = "sara@example.com"'))
        self.assertEqual({a['owner'] for a in cfg['agents']}, {'sara@example.com'})

    def test_subnets_stay_put(self):
        cfg = resolve(previous={'omar': 7})
        self.assertEqual(
            {a['id']: a['subnet'] for a in cfg['agents']}, {'sara': '10.207.1.0/24', 'omar': '10.207.7.0/24'}
        )
        again = resolve(previous=config.previous_subnets(config.public(cfg)))
        self.assertEqual([a['subnet'] for a in again['agents']], [a['subnet'] for a in cfg['agents']])

    def test_pair_domain_needs_the_id(self):
        self.assertIn('pair_domain', problems(PUBLIC, cluster__pair_domain='t3.example.com'))
        cfg = resolve(PUBLIC, cluster__pair_domain='{id}-t3.example.com')
        self.assertEqual(cfg['agents'][0]['pair_host'], 'sara-t3.example.com')

    def test_per_person_storage(self):
        text = BASE.replace('owner = "omar@example.com"', 'owner = "sara@example.com"')
        cfg = resolve(text, storage__mode='per-person', storage__person_sizes={'sara@example.com': '120G'})
        self.assertEqual(cfg['agents'][1]['path'], '/srv/agentlab/people/sara-example-com/omar')
        units = disks.units(cfg)
        self.assertEqual(
            [(u['image'], u['mount'], u['size']) for u in units],
            [('/srv/agentlab/disks/sara-example-com.img', '/srv/agentlab/people/sara-example-com', '120g')],
        )

    def test_shared_pool_image_override(self):
        cfg = resolve(storage__pool_size='100G', storage__pool_image='/opt/lab/agents-pool.img')
        self.assertEqual(disks.units(cfg)[0]['image'], '/opt/lab/agents-pool.img')
        self.assertEqual(disks.units(cfg)[0]['mount'], '/srv/agentlab/agents')
        self.assertEqual(disks.units(resolve()), [])

    def test_published_ports_only_for_one_person_without_a_gate(self):
        one = BASE.replace('owner = "omar@example.com"', 'owner = "sara@example.com"')
        text = one + '\n[agents.publish]\nt3 = 7101\n'
        self.assertIn('bypass the gate', problems(text))
        local = text.replace('mode = "cloudflare-access"', 'mode = "none"')
        cfg = resolve(local)
        self.assertEqual(cfg['agents'][1]['publish'], {'t3': 7101})
        two = (BASE + '\n[agents.publish]\nt3 = 7101\n').replace('mode = "cloudflare-access"', 'mode = "none"')
        self.assertIn('bypass the gate', problems(two))
        self.assertIn('unknown tool', problems(local.replace('t3 = 7101', 'ssh = 22')))

    def test_hostname_and_image_overrides(self):
        text = BASE.replace('id = "omar"', 'id = "omar"\nhostname = "box"\nimage = "mine/agent:1"')
        cfg = resolve(text)
        body = render.agent(cfg, cfg['agents'][1])['services']['agent']
        self.assertEqual((body['hostname'], body['image']), ('box', 'mine/agent:1'))
        self.assertNotIn('pull_policy', body)

    def test_color_is_optional_and_checked(self):
        cfg = resolve(BASE.replace('id = "omar"', 'id = "omar"\ncolor = "green"'))
        self.assertEqual([a['color'] for a in cfg['agents']], ['', 'green'])
        self.assertEqual(json.loads(config.to_json(cfg))['agents'][1]['color'], 'green')
        wrong = BASE.replace('id = "omar"', 'id = "omar"\ncolor = "mauve"')
        self.assertIn('must be one of green, pink', problems(wrong))


class DoctorHost(unittest.TestCase):
    def host(self, os_name, kernel, isolation='sysbox'):
        cfg = resolve(cluster__isolation=isolation)
        checks = doctor.Checks()
        with (
            mock.patch.object(doctor, '_os_name', return_value=os_name),
            mock.patch.object(doctor, '_kernel', return_value=kernel),
            mock.patch.object(doctor, '_wsl', return_value=False),
            mock.patch.object(doctor, '_mem_total', return_value=256 * 2**30),
            mock.patch.object(doctor, 'storage'),
        ):
            doctor.host(cfg, checks)
        return {c['id']: c for c in checks.items}

    def test_debian_13_with_its_6_12_kernel_is_fine(self):
        got = self.host(('Debian GNU/Linux 13 (trixie)', 'debian', '13'), (6, 12))
        self.assertEqual((got['os']['ok'], got['kernel']['ok']), (True, True))

    def test_kernel_thresholds_for_sysbox(self):
        self.assertEqual(self.host(('Ubuntu', 'ubuntu', '24.04'), (5, 15))['kernel']['severity'], 'warning')
        self.assertEqual(self.host(('Ubuntu', 'ubuntu', '24.04'), (5, 10))['kernel']['severity'], 'error')
        self.assertTrue(self.host(('Ubuntu', 'ubuntu', '24.04'), (5, 10), 'unconfined')['kernel']['ok'])

    def test_an_old_sysbox_drop_in_is_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            dropin = os.path.join(d, 'agentlab.conf')
            with open(dropin, 'w') as f:
                f.write('ExecStart=/usr/bin/sysbox-mgr --subid-range-size 262144\n')
            checks = doctor.Checks()
            with (
                mock.patch.object(doctor, 'OLD_SYSBOX_DROPIN', dropin),
                mock.patch.object(doctor, 'run', return_value=(0, '{"sysbox-runc":{}}')),
                mock.patch.object(doctor, '_active', return_value=True),
            ):
                doctor.sysbox(checks)
            got = {c['id']: c for c in checks.items}
            self.assertTrue(got['sysbox']['ok'])
            self.assertFalse(got['sysbox-dropin']['ok'])
            self.assertIn('agentctl install --only sysbox', got['sysbox-dropin']['fix'])


class Migration(unittest.TestCase):
    ONE = BASE.replace('owner = "omar@example.com"', 'owner = "sara@example.com"').replace(
        'mode = "cloudflare-access"', 'mode = "tailscale"'
    )

    def test_published_hub_names_its_one_owner(self):
        cfg = resolve(self.ONE, hub__publish=7190, cluster__publish_address='0.0.0.0')
        hub = render.core(cfg)['services']['hub']
        self.assertEqual(hub['ports'], ['0.0.0.0:7190:8080'])
        self.assertEqual(hub['environment']['HUB_PUBLISHED_OWNER'], 'sara@example.com')
        self.assertEqual(json.loads(config.to_json(cfg))['hub']['publish'], 7190)
        self.assertIn('bypass the gate', problems(hub__publish=7190))

    def test_published_ports_leave_tailscale_alone(self):
        cfg = resolve(self.ONE, hub__publish=7190)
        self.assertFalse(config.ports_only(cfg))
        for i, a in enumerate(cfg['agents']):
            a['publish'] = {'t3': 7101 + 10 * i}
        self.assertTrue(config.ports_only(cfg))
        self.assertEqual(install.step_env(cfg, '/etc/agentlab/cluster.toml')['AGENTLAB_SERVE'], '')
        env = render.agent(cfg, cfg['agents'][0])['services']['agent']['environment']
        self.assertEqual(env['AGENTLAB_PUBLISHED'], 't3=7101')
        self.assertEqual(env['AGENTLAB_PUBLISHED_HUB'], '7190')
        checks = doctor.Checks()
        with mock.patch.object(doctor, 'tailscale_cli', return_value=None):
            doctor._tailscale(cfg, checks)
        ids = {c['id'] for c in checks.items}
        self.assertIn('tailscale-ports', ids)
        self.assertFalse(ids & {'tailscale-serve', 'tailscale-https'})

    def test_extra_secrets_mount_into_the_hub(self):
        hub = render.core(resolve(self.ONE))['services']['hub']
        self.assertNotIn('HUB_EXTRA_SECRETS', hub['environment'])
        cfg = resolve(
            self.ONE,
            hub__extra_secrets='/srv/other/secrets/',
            hub__extra_secrets_map='/srv/other/map.json',
            hub__extra_secrets_label='Homelab',
        )
        hub = render.core(cfg)['services']['hub']
        self.assertIn('/srv/other/secrets:/extra-secrets', hub['volumes'])
        self.assertIn('/srv/other/map.json:/extra-secrets-map.json:ro', hub['volumes'])
        self.assertEqual(hub['environment']['HUB_EXTRA_SECRETS_LABEL'], 'Homelab')
        self.assertEqual(
            json.loads(config.to_json(cfg))['hub']['extra_secrets'],
            {'folder': '/srv/other/secrets', 'map': '/srv/other/map.json', 'label': 'Homelab'},
        )
        self.assertIn('must be an absolute path', problems(hub__extra_secrets='secrets'))
        self.assertIn('needs extra_secrets', problems(hub__extra_secrets_map='/srv/map.json'))

    def test_nightly_backups_can_be_off(self):
        self.assertTrue(resolve()['backups']['enabled'])
        cfg = resolve(backups__enabled=False)
        self.assertFalse(json.loads(config.to_json(cfg))['backups']['enabled'])
        self.assertEqual(install.step_env(cfg, '/etc/agentlab/cluster.toml')['AGENTLAB_BACKUPS'], '')
        self.assertIn('[backups] enabled must be true or false', problems(backups__enabled='no'))

    def test_phone_pushes_and_hub_state_on_the_host(self):
        hub = render.core(resolve(self.ONE))['services']['hub']
        self.assertNotIn('BARK_URL', hub['environment'])
        self.assertIn('/srv/agentlab/hub/data:/data', hub['volumes'])
        self.assertNotIn('volumes', render.core(resolve(self.ONE)))
        cfg = resolve(self.ONE, hub__bark_url='http://host.docker.internal:7192/', hub__bark_public='http://phone:7192')
        hub = render.core(cfg)['services']['hub']
        self.assertEqual(hub['environment']['BARK_URL'], 'http://host.docker.internal:7192')
        self.assertEqual(hub['environment']['BARK_PUBLIC'], 'http://phone:7192')
        self.assertIn('host.docker.internal:host-gateway', hub['extra_hosts'])
        self.assertNotIn('bark', json.loads(config.to_json(cfg)))
        self.assertIn('bark_url', problems(self.ONE, hub__bark_url='host:7192'))

    def test_the_hub_mounts_the_storage_root_not_each_agent(self):
        hub = render.core(resolve(self.ONE))['services']['hub']
        self.assertIn('/srv/agentlab/agents:/srv/agentlab/agents', hub['volumes'])  # no propagation: WSL refuses it
        more = resolve(self.ONE.replace('id = "sara"', 'id = "sara2"'))
        self.assertEqual(render.core(more)['services']['hub']['volumes'], hub['volumes'])
        hub = render.core(resolve(self.ONE, storage__mode='per-person'))['services']['hub']
        self.assertIn('/srv/agentlab/people:/srv/agentlab/people', hub['volumes'])
        self.assertIn('/srv/agentlab/people/sara-example-com:/srv/agentlab/people/sara-example-com', hub['volumes'])
        same_person = resolve(self.ONE.replace('id = "sara"', 'id = "sara2"'), storage__mode='per-person')
        self.assertEqual(render.core(same_person)['services']['hub']['volumes'], hub['volumes'])

    def test_a_new_agent_is_published_like_the_others(self):
        from agentlab import agents  # noqa: PLC0415

        text = self.ONE.replace('mode = "cloudflare-access"', 'mode = "none"')
        text += '\n[agents.publish]\nt3 = 7111\naccounts = 7112\nfiles = 7115\n\n[hub]\npublish = 7190\n'
        cfg = config.loads(text)
        self.assertEqual(agents.next_ports(cfg), {'t3': 7121, 'accounts': 7122, 'files': 7125})
        added = tomledit.add_agent(text, 'lina', 'sara@example.com', None, agents.next_ports(cfg))
        self.assertEqual(config.loads(added)['agents'][-1]['publish'], {'t3': 7121, 'accounts': 7122, 'files': 7125})
        self.assertEqual(agents.next_ports(resolve(self.ONE)), {})

    def test_tailscale_hub_address_carries_its_port(self):
        one = self.ONE.replace('hub_domain = "agents-hub.example.com"\n', '')
        env = render.agent(resolve(one), resolve(one)['agents'][0])['services']['agent']['environment']
        self.assertEqual(env['AGENTLAB_HUB_DOMAIN'], 'agents.example.com:8443')
        env = render.agent(self.cfg_cf(), self.cfg_cf()['agents'][0])['services']['agent']['environment']
        self.assertEqual(env['AGENTLAB_HUB_DOMAIN'], 'agents-hub.example.com')

    @staticmethod
    def cfg_cf():
        return resolve()

    def test_apply_takes_agents_off_extra_networks(self):
        from agentlab import deploy  # noqa: PLC0415

        cfg = resolve(self.ONE)
        plan = util.Plan(dry=True)

        def fake_run(cmd, check=True):
            if cmd[:2] == ['docker', 'ps']:
                return 0, 'c1' if 'label=com.docker.compose.project=agentlab-agent-sara' in cmd else ''
            return 0, json.dumps({'agentlab-sara': {}, 'coolifyuuid': {}})

        with mock.patch('agentlab.deploy.run', fake_run), contextlib.redirect_stdout(io.StringIO()):
            start = len(util.OUT.changes)
            deploy.isolate(cfg, plan)
        cmds = [c['command'] for c in util.OUT.changes[start:]]
        self.assertEqual(cmds, [['docker', 'network', 'disconnect', 'coolifyuuid', 'c1']])

    def test_coolify_plain_text_answers(self):
        from agentlab import coolify  # noqa: PLC0415

        class Reply(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        with tempfile.NamedTemporaryFile('w', suffix='.token') as tok:
            tok.write('t')
            tok.flush()
            cfg = resolve(coolify__token_file=tok.name)
            api = coolify.Api(cfg, opener=lambda req, timeout: Reply(b'4.5.3'))
            self.assertEqual(api.call('GET', '/version'), '4.5.3')
            api = coolify.Api(cfg, opener=lambda req, timeout: Reply(b'[{"uuid": "u"}]'))
            self.assertEqual(api.call('GET', '/servers'), [{'uuid': 'u'}])

    def test_backups_keep_the_hub_state(self):
        import datetime  # noqa: PLC0415
        import sqlite3  # noqa: PLC0415

        from agentlab import backup  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as d:
            cfg = resolve(self.ONE, cluster__data=d)
            os.makedirs(f'{d}/hub/data')
            with open(f'{d}/hub/data/notify.json', 'w') as f:
                f.write('{"device": "x"}')
            t3 = f'{cfg["agents"][0]["path"]}/home/.t3/userdata'
            os.makedirs(t3)
            sqlite3.connect(f'{t3}/statev2.sqlite').close()
            toml = f'{d}/cluster.toml'
            with open(toml, 'w') as f:
                f.write(self.ONE)
            with mock.patch('agentlab.backup.need_root'), mock.patch('agentlab.backup.say'):
                out = backup.run(cfg, toml, today=datetime.date(2026, 1, 2))
            self.assertEqual(out['databases'], 1)
            with open(f'{d}/backups/2026-01-02/hub/notify.json') as f:
                self.assertEqual(json.load(f), {'device': 'x'})

    def test_extra_stacks(self):
        cfg = resolve(hub__extra_stacks=['media-arr', 'media_jellyfin'])
        self.assertEqual(json.loads(config.to_json(cfg))['hub']['extra_stacks'], ['media-arr', 'media_jellyfin'])
        self.assertIn('extra_stacks', problems(hub__extra_stacks=['../etc']))

    def test_adopt_only_signed_in_agents(self):
        with tempfile.TemporaryDirectory() as d:
            signed, fresh = {'id': 'a', 'path': f'{d}/a'}, {'id': 'b', 'path': f'{d}/b'}
            os.makedirs(f'{d}/a/home/.codex')
            os.makedirs(f'{d}/b/home')
            with open(f'{d}/a/home/.codex/auth.json', 'w') as f:
                f.write('{}')
            with open(f'{d}/b/home/.claude.json', 'w') as f:
                f.write('{"numStartups": 1}')
            with (
                mock.patch('os.fchown'),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertTrue(apply.adopt(signed, util.Plan(False)))
                self.assertFalse(apply.adopt(signed, util.Plan(False)))
                self.assertFalse(apply.adopt(fresh, util.Plan(False)))
            self.assertTrue(os.path.isfile(f'{d}/a/home/.config/agent/onboarded'))
            self.assertFalse(os.path.exists(f'{d}/b/home/.config'))
            with open(f'{d}/b/home/.claude.json', 'w') as f:
                f.write('{"oauthAccount": {"emailAddress": "sara@example.com"}}')
            self.assertTrue(apply.signed_in(f'{d}/b/home'))


class Rendering(unittest.TestCase):
    def setUp(self):
        self.cfg = resolve(
            PUBLIC, cluster__pair_domain='{id}-t3.example.com', cluster__coolify_domain='agents-coolify.example.com'
        )
        self.edge = render.edge(self.cfg)
        self.routers = self.edge['http']['routers']
        self.middlewares = self.edge['http']['middlewares']

    def test_pass_one_strips_then_checks_then_hands_to_pass_two(self):
        ingress = {n: r for n, r in self.routers.items() if r['entryPoints'] != ['routed']}
        self.assertTrue(ingress)
        for name, r in ingress.items():
            first = self.middlewares[r['middlewares'][0]]['headers']['customRequestHeaders']
            for header in render.CLIENT_HEADERS:
                if header != 'X-Agentlab-Site':
                    self.assertEqual(first[header], '', f'{name} keeps a client {header}')
            if name.startswith('pair-'):
                self.assertTrue(r['service'].endswith('-t3'))
                self.assertEqual(len(r['middlewares']), 1)
                continue
            self.assertEqual(r['service'], 'pass2')
            self.assertEqual(r['middlewares'][-1], 'gate', name)
            self.assertIn(first['X-Agentlab-Site'], ('agent', 'hub', 'coolify'))

    def test_gate_answer_is_passed_on(self):
        self.assertEqual(self.middlewares['gate']['forwardAuth']['authResponseHeaders'], render.IDENTITY)
        self.assertEqual(self.middlewares['gate']['forwardAuth']['address'], 'http://gate:8080/verify')

    def test_pass_two_is_only_reachable_inside_the_edge(self):
        command = render.edge_service(self.cfg)['command']
        self.assertIn('--entrypoints.routed.address=127.0.0.1:8089', command)
        for name, r in self.routers.items():
            if r['service'] != 'pass2' and not name.startswith('pair-'):
                self.assertEqual(r['entryPoints'], ['routed'], name)
        for r in self.routers.values():
            if r['entryPoints'] == ['routed']:
                self.assertIn('Header(`X-Agentlab-Site`', r['rule'])

    def test_agent_routes_follow_the_gate(self):
        r = self.routers['sara-t3']
        self.assertIn('Header(`X-Agentlab-Agent`, `sara`)', r['rule'])
        self.assertGreater(self.routers['sara-accounts']['priority'], self.routers['menu']['priority'])
        self.assertGreater(self.routers['menu']['priority'], r['priority'])
        self.assertEqual(self.routers['sara-accounts']['middlewares'], ['strip-accounts'])
        self.assertNotIn('middlewares', self.routers['sara-terminal'])

    def test_edge_listens_on_loopback_only(self):
        self.assertEqual(render.edge_service(self.cfg)['ports'], ['127.0.0.1:8088:8088'])

    def test_agents_publish_nothing_and_have_a_fixed_address(self):
        body = render.agent(self.cfg, self.cfg['agents'][0])
        svc = body['services']['agent']
        self.assertNotIn('ports', svc)
        self.assertEqual(svc['networks']['agentlab-sara']['ipv4_address'], '10.207.1.2')
        self.assertEqual(svc['runtime'], 'sysbox-runc')
        self.assertNotIn('security_opt', svc)
        self.assertNotIn('user', svc)
        self.assertEqual(svc['environment']['AGENTLAB_ISOLATION'], 'sysbox')
        self.assertIn('/dev/net/tun', svc['devices'])
        self.assertEqual(body['networks'], {'agentlab-sara': {'external': True, 'name': 'agentlab-sara'}})
        for key in (
            'AGENT_ID',
            'AGENT_OWNER',
            'AGENTLAB_DOMAIN',
            'AGENTLAB_HUB_DOMAIN',
            'AGENTLAB_PAIR_HOST',
            'AGENTLAB_AUTH_MODE',
            'ANDROID_ENABLED',
            'ANDROID_SYSTEM_IMAGE',
        ):
            self.assertIn(key, svc['environment'])

    def test_file_manager_sidecar(self):
        stack = render.agent(self.cfg, self.cfg['agents'][0])['services']
        files = stack['files']
        self.assertEqual(files['image'], render.FILEBROWSER)
        self.assertEqual(files['user'], '1000:1000')
        self.assertEqual(list(files['networks']), ['agentlab-sara'])
        self.assertIn('/srv/agentlab/agents/sara/home:/home-agent:ro', files['volumes'])
        self.assertIn('/srv/agentlab/agents/sara/workspace:/workspace', files['volumes'])
        self.assertNotIn('ports', files)
        r = self.routers['sara-files']
        self.assertIn('PathPrefix(`/_agentlab/files`)', r['rule'])
        self.assertNotIn('middlewares', r)
        self.assertEqual(
            self.edge['http']['services']['sara-files']['loadBalancer']['servers'], [{'url': 'http://files-sara:80'}]
        )
        conf = render.files_config(self.cfg)
        for line in ('baseURL: /_agentlab/files', 'noauth: true', 'showHidden: true', 'folderName: node_modules'):
            self.assertIn(line, conf)

    def test_unconfined_and_android(self):
        cfg = resolve(cluster__isolation='unconfined', android__enabled=True)
        with mock.patch.object(render, 'kvm_gid', return_value=993):
            svc = render.agent(cfg, cfg['agents'][0])['services']['agent']
        self.assertNotIn('runtime', svc)
        self.assertIn('seccomp=unconfined', svc['security_opt'])
        self.assertEqual(svc['environment']['AGENTLAB_ISOLATION'], 'unconfined')
        self.assertIn('/dev/kvm', svc['devices'])
        self.assertEqual(svc['group_add'], ['993'])
        self.assertTrue(any(v.endswith(':/opt/android-sdk:ro') for v in svc['volumes']))

    def test_tinyauth_runs_before_the_gate(self):
        cfg = resolve(
            BASE.replace('mode = "cloudflare-access"', 'mode = "tinyauth"')
            + """
[auth.tinyauth]
domain = "login.example.com"
google_client_id_file = "/s/id"
google_client_secret_file = "/s/secret"
"""
        )
        edge = render.edge(cfg)
        self.assertEqual(edge['http']['routers']['in-agent']['middlewares'], ['site-agent', 'tinyauth', 'gate'])
        self.assertIn('Remote-Email', edge['http']['middlewares']['site-agent']['headers']['customRequestHeaders'])
        self.assertEqual(edge['http']['routers']['in-agent']['tls'], {'certResolver': 'le'})
        core = render.core(cfg)['services']
        self.assertIn('v5.1.3', core['tinyauth']['image'])
        self.assertIn('boss@example.com', core['tinyauth']['environment']['OAUTH_WHITELIST'])
        self.assertIn('80:80', core['edge']['ports'])
        cfg['auth']['allow_domains'] = ['example.com']
        whitelist = render.core(cfg)['services']['tinyauth']['environment']['OAUTH_WHITELIST'].split(',')
        self.assertIn('boss@example.com', whitelist)
        self.assertIn(r'/^[^@]+@example\.com$/', whitelist)

    def test_tailscale_uses_entrypoints_not_hosts(self):
        cfg = resolve(
            BASE.replace('mode = "cloudflare-access"', 'mode = "tailscale"').replace(
                'hub_domain = "agents-hub.example.com"\n', ''
            )
        )
        self.assertEqual(cfg['hub_domain'], cfg['domain'])
        routers = render.edge(cfg)['http']['routers']
        self.assertEqual(routers['in-hub']['entryPoints'], ['hubingress'])
        self.assertEqual(routers['in-agent']['entryPoints'], ['ingress'])
        self.assertIn('127.0.0.1:8090:8090', render.edge_service(cfg)['ports'])

    def test_published_ports_render(self):
        text = (
            BASE.replace('owner = "omar@example.com"', 'owner = "sara@example.com"').replace(
                'mode = "cloudflare-access"', 'mode = "none"'
            )
            + '\n[agents.publish]\nt3 = 7101\nterminal = 7104\nfiles = 7105\n'
        )
        cfg = resolve(text, cluster__publish_address='0.0.0.0', hub__publish=7190)
        services = render.agent(cfg, cfg['agents'][1])['services']
        self.assertEqual(services['agent']['ports'], ['0.0.0.0:7101:3773', '0.0.0.0:7104:7681'])
        self.assertEqual(services['files']['ports'], ['0.0.0.0:7105:80'])
        self.assertEqual(render.core(cfg)['services']['hub']['ports'], ['0.0.0.0:7190:8080'])

    def test_firewall_names_every_agent(self):
        rules = render.firewall(self.cfg)
        self.assertIn('elements = { 10.207.1.2, 10.207.2.2 }', rules)
        self.assertIn('ip daddr 10.207.0.0/16 ct state new counter drop', rules)
        self.assertIn('ip saddr @agents ct state established,related accept', rules)
        self.assertTrue(rules.index('delete table inet agentlab') < rules.index('table inet agentlab {'))

    def test_companion_runs_the_agents_checkout_read_only(self):
        cfg = resolve(BASE + '\n[[companions]]\nname = "helper"\nagent = "sara"\n')
        svc = render.companion(cfg, cfg['companions'][0])['services']['companion']
        self.assertIn('/srv/agentlab/agents/sara/workspace/companions/helper:/app:ro', svc['volumes'])
        self.assertEqual(svc['restart'], 'on-failure')
        self.assertEqual(svc['user'], '1000:1000')
        self.assertEqual(
            apply.companion_list(cfg, cfg['agents'][0]),
            [{'name': 'helper', 'display_name': 'helper', 'kind': 'slack'}],
        )

    def test_go_literal(self):
        self.assertEqual(render.go_literal('a.b+c@x.io'), 'a\\.b\\+c@x\\.io')
        self.assertTrue(re.fullmatch(render.go_literal('a.b'), 'a.b'))
        self.assertFalse(re.fullmatch(render.go_literal('a.b'), 'axb'))

    def test_every_file_renders(self):
        files = render.all_files(self.cfg)
        self.assertIn('compose/agentlab-core/docker-compose.yml', files)
        self.assertIn('compose/agentlab-agent-omar/docker-compose.yml', files)
        self.assertTrue(files['edge/dynamic.yml'].startswith('# GENERATED'))


class Yaml(unittest.TestCase):
    def test_ambiguous_strings_are_quoted(self):
        out = yaml.dump({'a': 'yes', 'b': '8080:80', 'c': 'plain', 'd': True, 'e': [], 'f': [{'x': 1, 'z': 'n'}]})
        self.assertIn('a: "yes"', out)
        self.assertIn('b: "8080:80"', out)
        self.assertIn('c: plain', out)
        self.assertIn('d: true', out)
        self.assertIn('e: []', out)
        self.assertIn('  - x: 1\n    z: "n"', out)
        self.assertIn('"y": 1', yaml.dump({'y': 1}))


class TomlEdits(unittest.TestCase):
    TEXT = """# keep me
[auth]
mode = "cloudflare-access"   # how people sign in

[auth.cloudflare]
team = "example"
audience = ""                # filled in by setup

[[agents]]
id = "sara"
owner = "sara@example.com"

[[agents]]
id = "omar"   # the second
owner = "omar@example.com"

# about android
[android]
enabled = true
"""

    def test_add_after_the_last_agent(self):
        out = tomledit.add_agent(self.TEXT, 'lina', 'lina@example.com')
        self.assertEqual([a['id'] for a in tomllib.loads(out)['agents']], ['sara', 'omar', 'lina'])
        self.assertLess(out.index('id = "lina"'), out.index('# about android'))

    def test_remove_keeps_comments_of_the_next_section(self):
        out = tomledit.remove_agent(self.TEXT, 'omar')
        self.assertEqual([a['id'] for a in tomllib.loads(out)['agents']], ['sara'])
        self.assertIn('# about android', out)
        self.assertIn('# keep me', out)
        with self.assertRaises(ValueError):
            tomledit.remove_agent(self.TEXT, 'nobody')

    def test_remove_takes_the_agents_own_subtables(self):
        text = self.TEXT.replace(
            'owner = "sara@example.com"\n', 'owner = "sara@example.com"\n\n[agents.publish]\nt3 = 7101\n'
        )
        out = tomledit.remove_agent(text, 'sara')
        self.assertNotIn('7101', out)
        self.assertEqual([a['id'] for a in tomllib.loads(out)['agents']], ['omar'])
        kept = tomledit.remove_agent(text, 'omar')
        self.assertEqual(tomllib.loads(kept)['agents'][0]['publish'], {'t3': 7101})

    def test_agent_limits_are_set_and_dropped(self):
        out = tomledit.add_agent(self.TEXT, 'lina', 'lina@example.com', {'memory': '8g', 'cpus': 2})
        self.assertEqual(
            tomllib.loads(out)['agents'][2], {'id': 'lina', 'owner': 'lina@example.com', 'memory': '8g', 'cpus': 2}
        )
        out = tomledit.set_agent_key(self.TEXT, 'omar', 'memory', '16g')
        self.assertEqual(tomllib.loads(out)['agents'][1]['memory'], '16g')
        again = tomledit.set_agent_key(out, 'omar', 'memory', '20g')
        self.assertEqual(again.count('memory ='), 1)
        self.assertNotIn('memory', tomllib.loads(tomledit.set_agent_key(again, 'omar', 'memory', None))['agents'][1])
        self.assertIn('# the second', again)
        with self.assertRaises(ValueError):
            tomledit.set_agent_key(self.TEXT, 'nobody', 'cpus', 2)

    def test_set_key_keeps_the_comment(self):
        out = tomledit.set_key(self.TEXT, 'auth.cloudflare', 'audience', 'abc123')
        self.assertIn('audience = "abc123"                # filled in by setup', out)
        self.assertEqual(tomllib.loads(out)['auth']['cloudflare']['audience'], 'abc123')
        added = tomledit.set_key(self.TEXT, 'backups', 'keep_days', 7)
        self.assertEqual(tomllib.loads(added)['backups']['keep_days'], 7)


class FakeCloudflare:
    def __init__(self):
        self.tunnels, self.configs, self.dns, self.policies, self.apps = [], {}, [], [], []
        self.routes, self.posture = [], []
        self.settings = {'gateway_proxy_enabled': True, 'gateway_udp_proxy_enabled': True}
        self.idps = [
            {'id': 'g1', 'type': 'google-apps', 'name': 'Google Workspace'},
            {'id': 'o1', 'type': 'onetimepin', 'name': 'One-time PIN'},
        ]
        self.writes = []
        # the account's device enrollment app (kept apart from self.apps)
        self.enroll = {
            'id': 'enroll',
            'type': 'warp',
            'name': 'Warp Login App',
            'policies': [{'id': 'db', 'precedence': 1}],
        }
        self.token = 'user'  # 'user' or 'account' token (they verify at different paths), or 'bad'
        self.denied = set()  # path fragments this token can't reach (the API answers 403)
        self.denied_writes = set()  # path fragments it may read but not change
        self.org = {'auth_domain': 'example.cloudflareaccess.com', 'warp_auth_session_duration': '24h'}
        self.refuse_app_flag = False  # the per-app client sign-in flag is refused with 12130
        self.own_groups = None  # the token's permission group names, when it may read itself
        self.calls = []
        self.ip_routes = []  # private IP routes on tunnels (teamnet)
        # device profiles: the default one in Exclude mode, as a new account has it
        self.profile = {'default': True, 'exclude': [{'address': '10.0.0.0/8'}]}
        self.profiles = []
        self.gateway = []  # Gateway rules (traffic policies)
        self.lists = {}  # Gateway list id -> items
        self.groups = {}  # Access group id -> group

    def call(self, method, path, body=None):
        self.calls.append((method, path))
        if method != 'GET':
            self.writes.append((method, path))
        if any(d in path for d in self.denied) or (method != 'GET' and any(d in path for d in self.denied_writes)):
            raise cloudflare.ApiError(f'Cloudflare {method} {path}: HTTP 403 [{{"code": 10000}}]', 403)
        if path.endswith('/tokens/verify'):
            if self.token == 'bad' or (self.token == 'user') != path.startswith('/user/'):
                raise util.Failed(f'Cloudflare GET {path}: HTTP 401')
            return {'status': 'active', 'id': 'tok1'}
        if path.endswith('/tokens/tok1'):
            if self.own_groups is None:
                raise cloudflare.ApiError(f'Cloudflare GET {path}: HTTP 403', 403)
            return {'policies': [{'permission_groups': [{'name': n} for n in self.own_groups]}]}
        warp_app = (
            '/access/apps' in path and method in ('POST', 'PUT') and (body or {}).get('allow_authenticate_via_warp')
        )
        if warp_app and (not self.org.get('warp_auth_session_duration') or self.refuse_app_flag):
            raise cloudflare.ApiError(
                f'Cloudflare {method} {path}: HTTP 400 [{{"code": 12130, "message": "allow_authenticate_via_warp '
                'cannot be set until a Cloudflare One Client Authentication session duration is set"}}]',
                400,
            )
        if '/access/apps' in path and method in ('POST', 'PUT') and (body or {}).get('domain'):
            public = [d.get('uri') for d in body.get('destinations', []) if d.get('type') == 'public']
            if body['domain'] not in public:
                raise cloudflare.ApiError(
                    f'Cloudflare {method} {path}: HTTP 400 [{{"code": 12130, "message": "access.api.error.'
                    'invalid_request: domain not included in destinations"}}]',
                    400,
                )
        path, _, query = path.partition('?')
        params = dict(p.split('=', 1) for p in query.split('&') if '=' in p)
        if path.endswith('/cfd_tunnel') and method == 'GET':
            return [t for t in self.tunnels if 'name' not in params or t['name'] == params['name']]
        if path.endswith('/cfd_tunnel') and method == 'POST':
            self.tunnels.append({'id': f't{len(self.tunnels) + 1}', 'name': body['name']})
            return self.tunnels[-1]
        if path.endswith('/configurations'):
            tid = path.split('/')[-2]
            if method == 'PUT':
                self.configs[tid] = body
            return self.configs.get(tid)
        if path.endswith('/token'):
            return 'tunnel-token'
        if path == '/zones':
            return [{'id': 'z1'}]
        if path.endswith('/dns_records') and method == 'GET':
            return [r for r in self.dns if 'name' not in params or r['name'] == params['name']]
        if path.endswith('/dns_records') and method == 'POST':
            self.dns.append({**body, 'id': f'd{len(self.dns)}'})
            return self.dns[-1]
        if '/dns_records/' in path and method == 'DELETE':
            self.dns = [r for r in self.dns if r['id'] != path.rsplit('/', 1)[1]]
            return {}
        if path.endswith('/zerotrust/routes/hostname'):
            if method == 'POST':
                self.routes.append({**body, 'id': f'r{len(self.routes) + 1}'})
                return self.routes[-1]
            return copy.deepcopy(self.routes)
        if '/zerotrust/routes/hostname/' in path and method == 'DELETE':
            self.routes = [r for r in self.routes if r['id'] != path.rsplit('/', 1)[1]]
            return {}
        if path.endswith('/devices/posture'):
            if method == 'POST':
                self.posture.append({**body, 'id': f'pc{len(self.posture) + 1}'})
                return self.posture[-1]
            return copy.deepcopy(self.posture)
        if path.endswith('/devices/policy'):
            return copy.deepcopy(self.profile)
        if path.endswith('/devices/policies'):
            return copy.deepcopy([{**self.profile, 'policy_id': 'def', 'name': 'Default'}, *self.profiles])
        if path.endswith('/devices/policy/include') and method == 'PUT':
            self.profile = {**self.profile, 'include': body}
            return body
        if '/devices/policy/' in path and path.endswith('/include') and method == 'PUT':
            pid = path.split('/')[-2]
            self.profiles = [{**p, 'include': body} if p['policy_id'] == pid else p for p in self.profiles]
            return body
        if path.endswith('/teamnet/routes'):
            return copy.deepcopy(self.ip_routes)
        if path.endswith('/devices/settings'):
            if method == 'PATCH':
                self.settings.update(body)
            return self.settings
        if '/access/apps/' in path and method == 'DELETE':
            self.apps = [a for a in self.apps if a['id'] != path.rsplit('/', 1)[1]]
            return {}
        if '/access/policies/' in path and method == 'DELETE':
            self.policies = [p for p in self.policies if p['id'] != path.rsplit('/', 1)[1]]
            return {}
        if path.endswith('/identity_providers'):
            return self.idps
        if path.endswith('/access/policies'):
            if method == 'POST':
                self.policies.append({**body, 'id': f'p{len(self.policies) + 1}'})
                return self.policies[-1]
            return copy.deepcopy(self.policies)
        if '/access/policies/' in path and method == 'PUT':
            pid = path.rsplit('/', 1)[1]
            self.policies = [{**body, 'id': pid} if p['id'] == pid else p for p in self.policies]
            return {}
        if path.endswith('/access/apps'):
            if method == 'POST':
                n = len(self.apps) + 1
                made = {**copy.deepcopy(body), 'id': f'a{n}', 'aud': f'aud{n}'}
                if body.get('type') == 'saas':
                    made['saas_app'] = {**body['saas_app'], 'client_id': f'cid{n}', 'client_secret': f'secret{n}'}
                self.apps.append(made)
                return copy.deepcopy(made)
            listed = copy.deepcopy([*self.apps, self.enroll])
            for a in listed:
                (a.get('saas_app') or {}).pop('client_secret', None)
            return listed
        if path.endswith('/access/apps/enroll') and method == 'PUT':
            self.enroll = {**body, 'id': 'enroll'}
            return self.enroll
        if '/access/apps/' in path and method == 'PUT':
            app = next(a for a in self.apps if a['id'] == path.rsplit('/', 1)[1])
            kept = {k: app[k] for k in ('id', 'aud') if k in app}
            app.clear()
            app.update({**body, **kept})
            return app
        if path.endswith('/access/organizations'):
            if method == 'PUT':
                self.org = dict(body)
            return dict(self.org)
        if path.endswith('/gateway/rules'):
            if method == 'POST':
                if any(r['precedence'] == body['precedence'] for r in self.gateway):
                    raise cloudflare.ApiError(f'Cloudflare POST {path}: HTTP 400 precedence in use', 400)
                self.gateway.append({**copy.deepcopy(body), 'id': f'g{len(self.writes)}'})
                return self.gateway[-1]
            return copy.deepcopy(self.gateway)
        if '/gateway/rules/' in path:
            rid = path.rsplit('/', 1)[1]
            if method == 'DELETE':
                self.gateway = [r for r in self.gateway if r['id'] != rid]
            elif method == 'PUT':
                self.gateway = [{**copy.deepcopy(body), 'id': rid} if r['id'] == rid else r for r in self.gateway]
            return {}
        if '/gateway/lists/' in path and path.endswith('/items'):
            return [{'value': v} for v in self.lists[path.split('/')[-2]]]
        if '/access/groups/' in path:
            return copy.deepcopy(self.groups[path.rsplit('/', 1)[1]])
        raise AssertionError(f'unexpected {method} {path}')


class Cloudflare(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = self.tmp.name
        os.makedirs(f'{d}/secrets')
        with open(f'{d}/secrets/cf.token', 'w') as f:
            f.write('api-token')
        self.config_path = f'{d}/cluster.toml'
        text = PUBLIC.replace('data = "/srv/agentlab"', f'data = "{d}"').replace(
            'hub_domain = "agents-hub.example.com"',
            'hub_domain = "agents-hub.example.com"\npair_domain = "{id}-t3.example.com"',
        ) + (f'\n[cloudflare]\naccount_id = "acc"\nzone = "example.com"\napi_token_file = "{d}/secrets/cf.token"\n')
        with open(self.config_path, 'w') as f:
            f.write(text)
        self.fake = FakeCloudflare()

    def run_setup(self, dry=False):
        cfg = config.load(self.config_path)
        with (
            mock.patch.object(cloudflare, 'api_for', return_value=self.fake),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            cloudflare.setup(cfg, util.Plan(dry), self.config_path)
        return cfg

    def test_setup_builds_everything_and_records_the_audience(self):
        self.run_setup()
        cfg = config.load(self.config_path)
        self.assertEqual(cfg['auth']['cloudflare']['audience'], 'aud1')
        ingress = self.fake.configs['t1']['config']['ingress']
        self.assertEqual(ingress[-1], {'service': 'http_status:404'})
        self.assertEqual(
            {r['hostname'] for r in ingress[:-1]},
            {'agents.example.com', 'agents-hub.example.com', 'sara-t3.example.com', 'omar-t3.example.com'},
        )
        self.assertEqual({r['name'] for r in self.fake.dns}, {r['hostname'] for r in ingress[:-1]})
        self.assertTrue(all(r['proxied'] and r['content'] == 't1.cfargotunnel.com' for r in self.fake.dns))
        people, apps_policy = self.fake.policies
        self.assertEqual(
            sorted(i['email']['email'] for i in people['include']),
            ['boss@example.com', 'omar@example.com', 'sara@example.com'],
        )
        self.assertEqual(apps_policy['decision'], 'bypass')
        people_app, apps_app = self.fake.apps
        self.assertEqual(
            sorted(d['uri'] for d in people_app['destinations']), ['agents-hub.example.com', 'agents.example.com']
        )
        self.assertEqual(
            sorted(d['uri'] for d in apps_app['destinations']), ['omar-t3.example.com', 'sara-t3.example.com']
        )
        with open(f'{self.tmp.name}/secrets/cloudflare-tunnel.token') as f:
            self.assertEqual(f.read(), 'tunnel-token')

    def test_second_run_changes_nothing(self):
        self.run_setup()
        before = len(self.fake.writes)
        self.run_setup()
        self.assertEqual(self.fake.writes[before:], [])

    def test_dry_run_writes_nothing(self):
        util.OUT.changes.clear()
        self.run_setup(dry=True)
        self.assertEqual(self.fake.writes, [])
        self.assertTrue(any('create tunnel' in c['change'] for c in util.OUT.changes))

    def test_login_method_pins_the_people_app_to_it(self):
        with open(self.config_path) as f:
            text = f.read()
        with open(self.config_path, 'w') as f:
            f.write(text.replace('team = "example"', 'team = "example"\nlogin_method = "google workspace"'))
        self.run_setup()
        people_app = self.fake.apps[0]
        self.assertEqual((people_app['allowed_idps'], people_app['auto_redirect_to_identity']), (['g1'], True))
        self.assertEqual(people_app['name'], 'agentlab-test')
        self.assertEqual(self.fake.policies[0]['name'], 'agentlab-test')

    def test_without_login_method_every_method_is_offered(self):
        with open(self.config_path) as f:
            text = f.read()
        with open(self.config_path, 'w') as f:
            f.write(text.replace('team = "example"', 'team = "example"\nlogin_method = "google workspace"'))
        self.run_setup()
        with open(self.config_path, 'w') as f:
            f.write(text)
        self.run_setup()
        people_app = next(a for a in self.fake.apps if a['name'] == 'agentlab-test')
        self.assertEqual((people_app['allowed_idps'], people_app['auto_redirect_to_identity']), ([], False))

    def test_unknown_login_method_names_the_real_ones(self):
        with open(self.config_path) as f:
            text = f.read()
        with open(self.config_path, 'w') as f:
            f.write(text.replace('team = "example"', 'team = "example"\nlogin_method = "Okta"'))
        with self.assertRaisesRegex(util.Failed, "'Google Workspace', 'One-time PIN'"):
            self.run_setup()

    def test_other_access_apps_and_policies_are_left_alone(self):
        self.fake.apps.append({'id': 'x1', 'name': 'payroll', 'destinations': [{'uri': 'pay.example.com'}]})
        self.fake.policies.append({'id': 'xp', 'name': 'staff', 'decision': 'allow', 'include': []})
        before = copy.deepcopy((self.fake.apps[0], self.fake.policies[0]))
        self.run_setup()
        self.run_setup()
        self.assertEqual((self.fake.apps[0], self.fake.policies[0]), before)
        self.assertFalse([w for w in self.fake.writes if w[1].endswith(('/x1', '/xp'))])

    def test_allow_domains_join_the_people_policy_and_stay(self):
        with open(self.config_path) as f:
            text = f.read()
        with open(self.config_path, 'w') as f:
            f.write(text.replace('[auth]\n', '[auth]\nallow_domains = ["example.com"]\n', 1))
        self.run_setup()
        include = self.fake.policies[0]['include']
        self.assertIn({'email_domain': {'domain': 'example.com'}}, include)
        self.assertIn({'email': {'email': 'sara@example.com'}}, include)
        writes = len(self.fake.writes)
        self.run_setup()
        self.assertEqual(len(self.fake.writes), writes)

    def probe(self):
        cfg = config.load(self.config_path)
        with mock.patch.object(cloudflare, 'api_for', return_value=self.fake):
            return cloudflare.probe_token(cfg)

    def test_token_probes_report_what_it_lacks(self):
        self.assertEqual(dict(self.probe()), {'tunnels': True, 'dns': True, 'access': True, 'idps': True})
        self.fake.token = 'account'
        self.assertTrue(all(ok for _, ok in self.probe()))
        for fragment, name in (
            ('/cfd_tunnel', 'tunnels'),
            ('/access/apps', 'access'),
            ('/identity_providers', 'idps'),
            ('/dns_records', 'dns'),
        ):
            self.fake.denied = {fragment}
            self.assertEqual([n for n, ok in self.probe() if not ok], [name])
        self.fake.denied = {'/zones'}
        self.assertEqual([n for n, ok in self.probe() if not ok], ['dns'])
        self.assertEqual(self.fake.writes, [])

    def test_the_organization_is_probed_only_when_the_team_is_unknown(self):
        cfg = config.load(self.config_path)
        cfg['auth']['cloudflare']['team'] = ''
        with mock.patch.object(cloudflare, 'api_for', return_value=self.fake):
            self.assertIn(('org', True), cloudflare.probe_token(cfg))
            self.fake.denied = {'/access/organizations'}
            self.assertIn(('org', False), cloudflare.probe_token(cfg))
        self.assertNotIn('org', dict(self.probe()))
        self.assertIn('Access: Organizations', cloudflare.PERMISSIONS['org'])

    def test_refused_token_is_one_clear_problem(self):
        self.fake.token = 'bad'
        self.assertIsNone(self.probe())
        checks = doctor.Checks()
        cfg = config.load(self.config_path)
        with mock.patch.object(cloudflare, 'api_for', return_value=self.fake):
            doctor._cloudflare_token(cfg, checks)
        self.assertEqual([(c['id'], c['ok']) for c in checks.items], [('cloudflare-token', False)])
        self.fake.token, self.fake.denied = 'user', {'/identity_providers'}
        checks = doctor.Checks()
        with mock.patch.object(cloudflare, 'api_for', return_value=self.fake):
            doctor._cloudflare_token(cfg, checks)
        failed = [c for c in checks.items if not c['ok']]
        self.assertEqual(len(failed), 1)
        self.assertIn('Access: Identity Providers → Read', failed[0]['message'])
        self.assertIn('Access: Identity Providers → Read', failed[0]['fix'])

    def test_people_policy_follows_the_agents(self):
        self.run_setup()
        with open(self.config_path) as f:
            cfg = config.loads(tomledit.remove_agent(f.read(), 'omar'))
        with (
            mock.patch.object(cloudflare, 'api_for', return_value=self.fake),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            cloudflare.sync_people(cfg, util.Plan(False))
        self.assertEqual(
            sorted(i['email']['email'] for i in self.fake.policies[0]['include']),
            ['boss@example.com', 'sara@example.com'],
        )


class AgentCompanions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = f'{self.tmp.name}/cluster.toml'
        with open(self.path, 'w') as f:
            f.write(
                BASE.replace('data = "/srv/agentlab"', f'data = "{self.tmp.name}"')
                + '\n[companion_policy]\nmax_per_agent = 2\n'
                + '\n[[companions]]\nname = "seeded-bot"\nagent = "omar"\n'
            )
        self.applied = []
        self.enterContext(mock.patch('agentlab.companions.need_root'))
        self.enterContext(
            mock.patch('agentlab.companions.apply.apply', side_effect=lambda *a, **k: self.applied.append(k))
        )
        self.enterContext(mock.patch('agentlab.companions.deploy.remove'))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        from agentlab import companions  # noqa: PLC0415

        self.companions = companions

    def names(self):
        return sorted(c['name'] for c in config.load(self.path)['companions'])

    def test_create_records_it_and_deploys_only_that_stack(self):
        self.companions.create(self.path, 'sara', 'helper', 'Helper')
        cfg = config.load(self.path)
        helper = next(c for c in cfg['companions'] if c['name'] == 'helper')
        self.assertEqual((helper['agent'], helper['display_name']), ('sara', 'Helper'))
        self.assertEqual(self.applied[-1]['only'], {'agentlab-companion-helper'})
        self.assertNotIn('created_by', json.loads(config.to_json(cfg))['companions'][0])

    def test_names_cap_and_policy(self):
        with self.assertRaisesRegex(util.Failed, 'taken'):
            self.companions.create(self.path, 'sara', 'seeded-bot')
        with self.assertRaisesRegex(util.Failed, '2-30'):
            self.companions.create(self.path, 'sara', 'X')
        self.companions.create(self.path, 'sara', 'one')
        self.companions.create(self.path, 'sara', 'two')
        with self.assertRaisesRegex(util.Failed, 'limit is 2'):
            self.companions.create(self.path, 'sara', 'three')
        self.companions.create(self.path, 'omar', 'three-b')
        with self.assertRaisesRegex(util.Failed, 'limit is 2'):
            self.companions.create(self.path, 'omar', 'three-c')
        with open(self.path) as f:
            text = f.read().replace('max_per_agent = 2', 'max_per_agent = 0')
        with open(self.path, 'w') as f:
            f.write(text)
        self.companions.create(self.path, 'sara', 'three')
        with open(self.path, 'w') as f:
            f.write(text.replace('max_per_agent = 0', 'max_per_agent = 0\nself_service = false'))
        with self.assertRaises(util.Needs):
            self.companions.create(self.path, 'omar', 'four')

    def test_only_the_companions_own_agent_removes_it_and_it_stays_removed(self):
        with self.assertRaisesRegex(util.Failed, 'has no companion'):
            self.companions.remove(self.path, 'sara', 'seeded-bot')
        os.makedirs(f'{self.tmp.name}/companions/seeded-bot')
        self.companions.remove(self.path, 'omar', 'seeded-bot')
        self.assertEqual(self.names(), [])
        archived = os.listdir(f'{self.tmp.name}/companions/.removed')
        self.assertTrue(archived[0].startswith('seeded-bot-'))

    def test_seeding_happens_once(self):
        cfg = config.load(self.path)
        self.assertEqual(cfg['seed'], ['seeded-bot'])
        self.companions.persist_seeds(cfg)
        again = config.load(self.path)
        self.assertEqual(again['seed'], [])
        self.assertEqual([c['name'] for c in again['companions']], ['seeded-bot'])
        self.assertNotIn('seed', json.loads(config.to_json(again)))


class AgentNative(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = f'{self.tmp.name}/cluster.toml'
        with open(self.path, 'w') as f:
            f.write(BASE.replace('data = "/srv/agentlab"', f'data = "{self.tmp.name}"'))
        util.OUT.json = False
        util.OUT.messages.clear()
        util.OUT.changes.clear()
        util.OUT.warnings.clear()
        self.enterContext(mock.patch('agentlab.privileges.elevate'))

    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = main.main(['--config', self.path, *argv])
        return code, out.getvalue()

    def test_json_output(self):
        code, out = self.run_cli('--json', 'agent', 'list')
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data['ok'])
        self.assertEqual([a['id'] for a in data['result']['agents']], ['sara', 'omar'])

    def test_global_options_may_come_last(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = main.main(['agent', 'list', '--json', '--config', self.path])
        self.assertEqual(code, 0)
        self.assertEqual([a['id'] for a in json.loads(out.getvalue())['result']['agents']], ['sara', 'omar'])

    def test_destructive_needs_yes_and_says_so(self):
        code, out = self.run_cli('--json', 'agent', 'remove', 'omar')
        self.assertEqual(code, util.NEEDS)
        data = json.loads(out)
        self.assertIn('--yes', data['error'])
        with open(self.path) as f:
            self.assertIn('id = "omar"', f.read())

    def test_bad_config_fails_with_exit_1(self):
        with open(self.path, 'a') as f:
            f.write('\n[mystery]\n')
        code, out = self.run_cli('--json', 'config')
        self.assertEqual(code, util.FAILED)
        self.assertIn('unknown section [mystery]', json.loads(out)['error'])

    def test_dry_run_apply_lists_changes_and_touches_nothing(self):
        with (
            mock.patch('agentlab.deploy.run', return_value=(1, '')),
            mock.patch('agentlab.images.present', return_value=True),
            mock.patch('agentlab.disks.run', return_value=(1, '')),
        ):
            code, out = self.run_cli('--json', 'apply', '--dry-run')
        data = json.loads(out)
        self.assertEqual(code, 0, data['error'])
        changes = [c['change'] for c in data['changes']]
        self.assertTrue(any(c.startswith('create network agentlab-sara (10.207.1.0/24)') for c in changes), changes)
        self.assertTrue(any('deploy agentlab-core' in c for c in changes))
        self.assertFalse(all(c['done'] for c in data['changes']))
        self.assertEqual(os.listdir(self.tmp.name), ['cluster.toml'])


class DiskSizes(unittest.TestCase):
    GIB = 2**30

    def per_person(self, **storage):
        return resolve(storage__mode='per-person', **{f'storage__{k}': v for k, v in storage.items()})

    def sizes(self, cfg, host_gib):
        with mock.patch.object(disks, 'host_bytes', return_value=host_gib * self.GIB):
            return {u['name']: u['size'] for u in disks.units(cfg)}

    def test_auto_splits_the_host_after_its_reserve(self):
        cfg = self.per_person(person_size='auto', host_reserve='100G')
        self.assertEqual(self.sizes(cfg, 500), {'sara-example-com': '200g', 'omar-example-com': '200g'})
        cfg = self.per_person(person_size='auto')  # 15 % by default
        self.assertEqual(self.sizes(cfg, 1000)['sara-example-com'], '425g')

    def test_auto_leaves_fixed_sizes_alone(self):
        cfg = self.per_person(person_size='auto', host_reserve='100G', person_sizes={'omar@example.com': '100G'})
        self.assertEqual(self.sizes(cfg, 500), {'sara-example-com': '300g', 'omar-example-com': '100g'})

    def test_auto_with_nothing_left_fails(self):
        cfg = self.per_person(person_size='auto', host_reserve='600G')
        with self.assertRaises(util.Failed):
            self.sizes(cfg, 500)

    def test_bad_reserve_is_a_config_problem(self):
        self.assertIn('host_reserve', problems(storage__host_reserve='120%'))
        self.assertIn('host_reserve', problems(storage__host_reserve='lots'))

    def plan_shrink(self, used_gib, have_gib, want_gib, busy=False, free_gib=500, mounted=True):
        cfg = self.per_person()
        u = disks.units(cfg)[0]
        plan = mock.Mock()
        with (
            mock.patch.object(disks.os.path, 'ismount', return_value=mounted),
            mock.patch.object(disks, 'usage', return_value={'used': used_gib * self.GIB, 'avail': free_gib * self.GIB}),
            mock.patch.object(disks.deploy, 'agent_busy', return_value=busy),
            mock.patch.object(disks, 'warn') as warned,
        ):
            disks.shrink(cfg, u, have_gib * self.GIB, want_gib * self.GIB, plan)
        return [c.args[0] for c in plan.do.call_args_list], warned.call_args_list

    def test_shrink_goes_to_the_asked_size_when_the_data_fits(self):
        done, _ = self.plan_shrink(50, 110, 88)
        self.assertEqual(len(done), 1)
        self.assertIn('110 -> 88 GiB (stops agentlab-agent-sara', done[0])

    def test_shrink_stops_short_of_the_data(self):
        done, warned = self.plan_shrink(90, 110, 88)
        self.assertIn('110 -> 99 GiB', done[0])
        self.assertTrue(warned)

    def test_shrink_waits_when_it_is_not_safe_yet(self):
        self.assertEqual(self.plan_shrink(100, 110, 88)[0], [])  # the data needs the room
        self.assertEqual(self.plan_shrink(10, 110, 109.5)[0], [])  # too small a step to stop anyone for
        self.assertEqual(self.plan_shrink(10, 110, 88, busy=True)[0], [])  # mid-turn
        self.assertEqual(self.plan_shrink(30, 110, 88, free_gib=40)[0], [])  # no host room for the moved blocks
        self.assertEqual(self.plan_shrink(10, 110, 88, mounted=False)[0], [])  # data unmeasured

    def run_shrink(self, rcs=None, fail=None):
        """`rcs`: {command or 'e2fsck -n': exit code}; `fail`: the command that raises."""
        tmp = self.enterContext(tempfile.TemporaryDirectory())
        img = f'{tmp}/sara.img'
        with open(img, 'wb') as f:
            f.truncate(8 << 20)
        u = {'name': 'sara', 'image': img, 'mount': f'{tmp}/mnt', 'stacks': ['agentlab-agent-sara']}
        mounted, calls, states = [True], [], iter(['running', 'running', 'exited'])
        rcs = rcs or {}

        def run(cmd, check=True):
            name = 'e2fsck -n' if cmd[:3] == ['e2fsck', '-f', '-n'] else cmd[0]
            calls.append(name)
            if name == 'resize2fs':
                open(disks.undo_file(img), 'w').close()
            if name == 'losetup':
                return 0, '/dev/loop9'
            if name == fail:
                raise util.Failed(f'{name} failed')
            if name in ('umount', 'mount'):
                mounted[0] = name == 'mount'
            return rcs.get(name, 0), ''

        with (
            mock.patch.object(disks, 'run', side_effect=run),
            mock.patch.object(disks.os.path, 'ismount', side_effect=lambda p: mounted[0]),
            mock.patch.object(disks, 'fs_bytes', return_value=4 << 20),
            mock.patch.object(
                disks.deploy, 'stack_containers', side_effect=lambda *a: [{'state': next(states, 'exited')}]
            ),
            mock.patch.object(disks.deploy, 'stop', side_effect=lambda *a: calls.append('stop')),
            mock.patch.object(disks.deploy, 'start', side_effect=lambda *a: calls.append('start')),
            mock.patch.object(disks, 'warn') as warned,
        ):
            disks._shrink(self.per_person(), u, 4 << 20, sleep=lambda s: None)
        left = os.path.exists(disks.undo_file(img))
        return calls, os.path.getsize(img), mounted[0], left, [w.args[0] for w in warned.call_args_list]

    def test_shrink_runs_offline_checks_and_cuts_the_image_last(self):
        calls, size, mounted, left, warned = self.run_shrink()
        self.assertEqual(
            calls, ['stop', 'umount', 'e2fsck', 'losetup', 'resize2fs', 'losetup', 'e2fsck -n', 'mount', 'start']
        )
        self.assertEqual((size, mounted, left, warned), (4 << 20, True, False, []))

    def test_a_refused_shrink_keeps_the_image_and_brings_everything_back(self):
        calls, size, mounted, left, warned = self.run_shrink(fail='resize2fs')
        self.assertEqual(calls[-5:], ['resize2fs', 'losetup', 'e2fsck -n', 'mount', 'start'])
        self.assertEqual((size, mounted, left), (8 << 20, True, False))
        self.assertIn('not shrunk', warned[0])

    def test_a_damaged_shrink_is_undone(self):
        calls, size, mounted, left, _ = self.run_shrink(rcs={'e2fsck -n': 4})
        self.assertIn('e2undo', calls)
        self.assertEqual((size, mounted, left, calls[-1]), (8 << 20, True, False, 'start'))

    def test_a_failed_undo_leaves_the_disk_alone(self):
        calls, size, mounted, left, warned = self.run_shrink(rcs={'e2fsck -n': 4}, fail='e2undo')
        self.assertEqual((size, mounted, left), (8 << 20, False, True))
        self.assertNotIn('start', calls)
        self.assertIn('e2undo', warned[-1])

    def test_an_interrupted_shrink_is_checked_before_mounting(self):
        tmp = self.enterContext(tempfile.TemporaryDirectory())
        img = f'{tmp}/sara.img'
        for path in (img, disks.undo_file(img)):
            open(path, 'w').close()
        u = {'name': 'sara', 'image': img, 'mount': f'{tmp}/mnt', 'size': '1g', 'stacks': []}
        plan = mock.Mock()
        with mock.patch.object(disks.os.path, 'ismount', return_value=False):
            disks.ensure_unit(self.per_person(), u, plan)
        self.assertEqual(
            [c.args[0] for c in plan.do.call_args_list],
            ['roll back the interrupted shrink of the sara disk', 'mount the sara disk at ' + f'{tmp}/mnt'],
        )


class Privileges(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = f'{self.tmp.name}/cluster.toml'
        with open(self.path, 'w') as f:
            f.write(BASE.replace('data = "/srv/agentlab"', f'data = "{self.tmp.name}"'))
        self.enterContext(mock.patch('agentlab.privileges.is_root', return_value=False))
        self.enterContext(mock.patch('agentlab.privileges.docker_ok', return_value=True))
        self.enterContext(mock.patch('agentlab.privileges.shutil.which', return_value='/usr/bin/sudo'))

    def args(self, *argv):
        return main.parser().parse_args(main.global_first(['--config', self.path, *argv]))

    def test_which_commands_elevate(self):
        root = [
            ['init'],
            ['install'],
            ['apply'],
            ['cloudflare', 'setup'],
            ['backup', 'run'],
            ['backup', 'restore', '2026-01-01', 'sara'],
            ['agent', 'add', 'kim', 'kim@example.com'],
            ['agent', 'remove', 'omar', '--yes'],
            ['agent', 'adopt', 'sara'],
            ['companion', 'create', 'sara', 'helper'],
            ['companion', 'remove', 'sara', 'helper'],
        ]
        plain = [
            ['doctor'],
            ['status'],
            ['config'],
            ['config', 'edit'],
            ['agent', 'list'],
            ['backup', 'list'],
            ['apply', '--dry-run'],
            ['agent', 'add', 'kim', 'kim@example.com', '--dry-run'],
            ['agent', 'remove', 'omar'],
            ['images', 'build'],
        ]
        for argv in root:
            self.assertTrue(privileges.needs_root(self.args(*argv)), argv)
        for argv in plain:
            self.assertFalse(privileges.needs_root(self.args(*argv)), argv)

    def test_dry_run_and_images_elevate_when_they_cannot_read(self):
        with mock.patch('agentlab.privileges.docker_ok', return_value=False):
            self.assertTrue(privileges.needs_root(self.args('apply', '--dry-run')))
            self.assertTrue(privileges.needs_root(self.args('images', 'build')))
        with mock.patch('agentlab.privileges.readable', return_value=False):
            self.assertTrue(privileges.needs_root(self.args('apply', '--dry-run')))
            self.assertTrue(privileges.needs_root(self.args('agent', 'remove', 'omar')))

    def test_root_and_read_only_never_call_sudo(self):
        execv = mock.Mock()
        privileges.elevate(self.args('doctor'), ['doctor'], execv=execv)
        with mock.patch('agentlab.privileges.is_root', return_value=True):
            privileges.elevate(self.args('apply'), ['apply'], execv=execv)
        execv.assert_not_called()

    def test_agents_get_exit_2_instead_of_a_password_prompt(self):
        refused = mock.Mock(return_value=mock.Mock(returncode=1))
        execv = mock.Mock()
        with self.assertRaises(util.Needs) as cm:
            privileges.elevate(self.args('--json', 'apply'), ['--json', 'apply'], execv=execv, probe=refused)
        execv.assert_not_called()
        self.assertEqual(cm.exception.result['needs'], 'sudo')
        self.assertEqual(cm.exception.result['command'], 'sudo agentctl --json apply')
        refused.assert_called_once_with(['sudo', '-n', 'true'], capture_output=True, check=False)

    def test_needs_sudo_is_exit_2_json_from_main(self):
        refused = mock.Mock(return_value=mock.Mock(returncode=1))
        out = io.StringIO()
        with (
            mock.patch('agentlab.privileges.subprocess.run', refused),
            # pin root and no sudo so only the refusal is under test
            mock.patch('agentlab.privileges.is_root', return_value=False),
            mock.patch('agentlab.privileges.shutil.which', return_value='/usr/bin/sudo'),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            code = main.main(['--config', self.path, '--json', 'install'])
        data = json.loads(out.getvalue())
        self.assertEqual(code, util.NEEDS)
        self.assertEqual(data['result']['needs'], 'sudo')
        self.assertIn('sudo agentctl', data['error'])

    def test_allowed_sudo_reruns_the_same_command_non_interactively(self):
        allowed = mock.Mock(return_value=mock.Mock(returncode=0))
        execv = mock.Mock()
        privileges.elevate(self.args('--json', 'apply'), ['--json', 'apply'], execv=execv, probe=allowed)
        sudo, cmd = execv.call_args.args
        self.assertEqual(sudo, '/usr/bin/sudo')
        self.assertEqual(cmd[:2], ['sudo', '-n'])
        self.assertEqual(cmd[2:4], [sys.executable, privileges.SCRIPT])
        self.assertEqual(cmd[-4:], ['--config', os.path.abspath(self.path), '--json', 'apply'])

    def test_a_person_at_a_terminal_gets_the_password_prompt(self):
        execv = mock.Mock()
        with mock.patch('agentlab.privileges.sys.stdin.isatty', return_value=True):
            privileges.elevate(self.args('apply'), ['apply'], execv=execv)
        self.assertNotIn('-n', execv.call_args.args[1])


class Group:
    def __init__(self, gid, members):
        self.gr_gid, self.gr_mem = gid, members


class Init(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.etc = f'{self.tmp.name}/etc/agentlab/cluster.toml'
        self.bin = f'{self.tmp.name}/bin'
        self.groups = {}
        self.ran = []
        self.enterContext(mock.patch('agentlab.util.run', side_effect=self.fake_run))
        self.enterContext(mock.patch('agentlab.init.os.chown'))
        util.OUT.changes.clear()

    def fake_run(self, cmd, **_):
        self.ran.append(cmd)
        if cmd[0] == 'groupadd':
            self.groups[cmd[-1]] = Group(1234, [])
        if cmd[0] == 'usermod':
            self.groups[cmd[2]].gr_mem.append(cmd[3])
        return 0, ''

    def init(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return init.init(self.etc, bin_dir=self.bin, user='sam', get=self.groups.get)

    def test_first_run_links_groups_and_starts_the_config(self):
        result = self.init()
        self.assertEqual(os.readlink(f'{self.bin}/agentctl'), os.path.join(init.REPO, 'cli', 'agentctl'))
        self.assertIn(['groupadd', '--system', 'agentlab'], self.ran)
        self.assertIn(['usermod', '-aG', 'agentlab', 'sam'], self.ran)
        with open(self.etc) as f, open(EXAMPLE) as ex:
            self.assertEqual(f.read(), ex.read())
        self.assertEqual(os.stat(self.etc).st_mode & 0o777, 0o640)
        self.assertIn('newgrp', result['next'][0])

    def test_rerun_changes_nothing_and_never_overwrites_the_config(self):
        self.init()
        with open(self.etc, 'w') as f:
            f.write('# mine\n')
        self.groups['agentlab'].gr_gid = os.stat(self.etc).st_gid
        self.ran.clear()
        util.OUT.changes.clear()
        result = self.init()
        self.assertEqual(self.ran, [])
        self.assertEqual(util.OUT.changes, [])
        with open(self.etc) as f:
            self.assertEqual(f.read(), '# mine\n')
        self.assertNotIn('newgrp', result['next'][0])

    def test_a_config_placed_before_init_gets_the_group_but_keeps_its_content(self):
        os.makedirs(os.path.dirname(self.etc))
        with open(self.etc, 'w') as f:
            f.write('# placed by hand\n')
        os.chmod(self.etc, 0o600)
        self.init()
        self.assertEqual(os.stat(self.etc).st_mode & 0o777, 0o640)
        init.os.chown.assert_any_call(self.etc, 0, 1234)
        with open(self.etc) as f:
            self.assertEqual(f.read(), '# placed by hand\n')

    def test_refuses_to_replace_a_real_file_on_path(self):
        os.makedirs(self.bin)
        with open(f'{self.bin}/agentctl', 'w') as f:
            f.write('something else')
        with self.assertRaises(util.Failed):
            self.init()


class ConfigEdit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = f'{self.tmp.name}/cluster.toml'
        self.good = BASE.replace('data = "/srv/agentlab"', f'data = "{self.tmp.name}"')
        with open(self.path, 'w') as f:
            f.write(self.good)

    def edit(self, new_text):
        def editor(cmd, **_):
            with open(cmd[-1], 'w') as f:
                f.write(new_text)
            return 0, ''

        with contextlib.redirect_stdout(io.StringIO()):
            return init.edit(self.path, editor='nano', runner=editor, isatty=True)

    def test_valid_edit_is_checked(self):
        self.assertEqual(self.edit(self.good)['agents'], 2)

    def test_invalid_edit_fails_with_the_error(self):
        with self.assertRaises(util.Failed) as cm:
            self.edit(self.good + '\n[mystery]\n')
        self.assertIn('unknown section [mystery]', str(cm.exception))

    def test_needs_a_terminal(self):
        with self.assertRaises(util.Needs):
            init.edit(self.path, isatty=False)


if __name__ == '__main__':
    unittest.main()


class PrivateNetwork(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = self.tmp.name
        os.makedirs(f'{d}/secrets')
        with open(f'{d}/secrets/cf.token', 'w') as f:
            f.write('api-token')
        self.config_path = f'{d}/cluster.toml'
        self.text = BASE.replace('data = "/srv/agentlab"', f'data = "{d}"') + (
            f'\n[cloudflare]\naccount_id = "acc"\nzone = "example.com"\napi_token_file = "{d}/secrets/cf.token"\n'
        )
        self.write(self.text)
        self.fake = FakeCloudflare()

    def write(self, text):
        with open(self.config_path, 'w') as f:
            f.write(text)

    def run_setup(self):
        cfg = config.load(self.config_path)
        with (
            mock.patch.object(cloudflare, 'api_for', return_value=self.fake),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            cloudflare.setup(cfg, util.Plan(False), self.config_path)
        return cfg

    def netzero_like(self):
        """An account with its own setup: enrollment for a reusable email list, and a rule only that list passes."""
        self.fake.lists['dbteam'] = ['boss@example.com', 'dev@other.com']
        self.fake.policies.append(
            {'id': 'db', 'name': 'DB team', 'decision': 'allow', 'include': [{'email_list': {'id': 'dbteam'}}]}
        )
        theirs = {
            'id': 'theirs',
            'name': 'Only the DB team over the tunnel',
            'action': 'block',
            'filters': ['l4'],
            'traffic': 'net.dst.ip in {10.0.0.0/8}',
            'identity': 'not(identity.email in $dbteam)',
            'precedence': 1000,
            'enabled': True,
        }
        self.fake.gateway.append(dict(theirs))
        return theirs

    def ours(self):
        return {r['name']: r for r in self.fake.gateway if r['name'].startswith('agentlab-test')}

    def test_gateway_rules_go_ahead_of_the_accounts_own_and_isolate_newcomers(self):
        theirs = self.netzero_like()
        self.run_setup()
        ours = self.ours()
        self.assertEqual(
            [
                (n, r['action'], r['filters'], r['precedence'])
                for n, r in sorted(ours.items(), key=lambda i: i[1]['precedence'])
            ],
            [
                ('agentlab-test allow', 'allow', ['l4'], 998),
                ('agentlab-test only agentlab', 'block', ['l4'], 999),
            ],
        )
        allow = ours['agentlab-test allow']
        self.assertEqual(allow['traffic'], 'net.dst.ip == 10.207.0.2 and net.dst.port in {80 443}')
        for email in ('boss@example.com', 'sara@example.com', 'omar@example.com'):
            self.assertIn(email, allow['identity'])
        block = ours['agentlab-test only agentlab']
        self.assertIn('sara@example.com', block['identity'])
        self.assertNotIn('boss@example.com', block['identity'])  # already on the DB team's list
        self.assertTrue(block['traffic'].startswith('net.dst.ip in {10.0.0.0/8 '))
        self.assertEqual(next(r for r in self.fake.gateway if r['id'] == 'theirs'), theirs)  # untouched
        before = len(self.fake.writes)
        self.run_setup()
        self.assertEqual(self.fake.writes[before:], [])

    def test_gateway_rules_follow_the_people_and_the_accounts_order(self):
        self.netzero_like()
        self.run_setup()
        self.write(self.text.replace('owner = "omar@example.com"', 'owner = "dev@other.com"'))
        self.run_setup()
        ours = self.ours()
        self.assertIn('dev@other.com', ours['agentlab-test allow']['identity'])
        self.assertNotIn('dev@other.com', ours['agentlab-test only agentlab']['identity'])
        self.assertNotIn('omar@example.com', ours['agentlab-test allow']['identity'])
        self.fake.gateway[0]['precedence'] = 500  # the admin moved their rule up
        self.run_setup()
        self.assertEqual(sorted(r['precedence'] for r in self.ours().values()), [498, 499])

    def test_unreadable_enrollment_rules_keep_everyone_isolated(self):
        self.fake.policies.append(
            {
                'id': 'db',
                'name': 'Okta',
                'decision': 'allow',
                'include': [{'okta': {'name': 'eng', 'identity_provider_id': 'x'}}],
            }
        )
        with mock.patch.object(gateway, 'warn') as warned:
            self.run_setup()
        self.assertIn('Okta', warned.call_args.args[0])
        block = self.ours()['agentlab-test only agentlab']
        self.assertIn('boss@example.com', block['identity'])

    def test_http_rules_have_their_own_order(self):
        self.netzero_like()
        dni = {
            'id': 'h',
            'name': 'Do not inspect',
            'precedence': 0,
            'action': 'off',
            'filters': ['http'],
            'traffic': 'x',
        }
        self.fake.gateway.append(dict(dni))
        self.run_setup()
        ours = sorted(r['precedence'] for r in self.ours().values())
        self.assertEqual(ours, [998, 999])  # just ahead of the account's network rule at 1000
        self.assertEqual(next(r for r in self.fake.gateway if r['id'] == 'h'), dni)

    def test_the_accounts_first_rules_move_down_just_enough(self):
        theirs = self.netzero_like()
        theirs_first = {
            'id': 'x',
            'name': 'first',
            'precedence': 0,
            'action': 'allow',
            'filters': ['l4'],
            'traffic': 'a',
        }
        theirs_next = {**theirs_first, 'id': 'y', 'name': 'next', 'precedence': 1, 'version': 3}
        theirs_far = {**theirs_first, 'id': 'z', 'name': 'far', 'precedence': 5}
        self.fake.gateway += [dict(theirs_first), dict(theirs_next), dict(theirs_far)]
        self.run_setup()
        by_name = {r['name']: r for r in self.fake.gateway}
        self.assertEqual(
            [
                (n, by_name[n]['precedence'])
                for n in ('agentlab-test allow', 'agentlab-test only agentlab', 'first', 'next', 'far')
            ],
            [('agentlab-test allow', 2), ('agentlab-test only agentlab', 3), ('first', 4), ('next', 5), ('far', 6)],
        )
        self.assertEqual(
            {k: v for k, v in by_name['first'].items() if k != 'precedence'},
            {k: v for k, v in theirs_first.items() if k != 'precedence'},
        )
        self.assertNotIn('version', by_name['next'])  # bookkeeping is never sent back
        self.assertEqual(by_name['Only the DB team over the tunnel']['precedence'], theirs['precedence'])
        before = len(self.fake.writes)
        self.run_setup()
        self.assertEqual(self.fake.writes[before:], [])

    def test_private_is_the_default_and_has_no_public_hostnames(self):
        self.assertTrue(config.private_network(config.load(self.config_path)))
        self.run_setup()
        self.assertEqual(self.fake.dns, [])
        conf = self.fake.configs['t1']['config']
        self.assertEqual(conf['ingress'], [{'service': 'http_status:404'}])
        self.assertTrue(conf['warp-routing']['enabled'])
        self.assertEqual(
            sorted((r['hostname'], r['tunnel_id'], r['comment']) for r in self.fake.routes),
            [('agents-hub.example.com', 't1', 'agentlab-test'), ('agents.example.com', 't1', 'agentlab-test')],
        )
        (app,) = self.fake.apps
        self.assertEqual({d['type'] for d in app['destinations']}, {'private'})
        self.assertEqual({d['port_range'] for d in app['destinations']}, {'80'})
        self.assertTrue(app['allow_authenticate_via_warp'])

    def test_second_run_changes_nothing(self):
        self.run_setup()
        before = len(self.fake.writes)
        self.run_setup()
        self.assertEqual(self.fake.writes[before:], [])

    def test_switching_from_public_removes_only_agentlabs_public_objects(self):
        self.write(
            self.text.replace('team = "example"', 'team = "example"\nnetwork = "public"').replace(
                'hub_domain = "agents-hub.example.com"',
                'hub_domain = "agents-hub.example.com"\npair_domain = "{id}-t3.example.com"',
            )
        )
        self.run_setup()
        self.fake.dns.append({'id': 'mine', 'name': 'shop.example.com', 'type': 'A', 'content': '1.2.3.4'})
        self.fake.apps.append({'id': 'x1', 'name': 'payroll', 'destinations': [{'uri': 'pay.example.com'}]})
        self.write(self.text)
        self.run_setup()
        self.assertEqual([r['id'] for r in self.fake.dns], ['mine'])
        self.assertEqual(sorted(a['name'] for a in self.fake.apps), ['agentlab-test', 'payroll'])
        self.assertNotIn('agentlab-test apps', [p['name'] for p in self.fake.policies])
        self.assertEqual({d['type'] for d in self.fake.apps[0]['destinations']}, {'private'})

    def test_include_mode_profiles_get_the_team_domain_and_the_sign_in_provider(self):
        own = [{'host': 'intranet.example.com'}]
        self.fake.profile = {'default': True, 'include': list(own)}
        self.fake.profiles = [
            {'policy_id': 'mac', 'name': 'Macs', 'include': list(own)},
            {'policy_id': 'ops', 'name': 'Ops', 'exclude': [{'address': '10.0.0.0/8'}]},
        ]
        self.fake.idps = [{'id': 'g1', 'type': 'google-apps', 'name': 'Google'}]
        self.run_setup()
        want = ['intranet.example.com', 'example.cloudflareaccess.com', 'accounts.google.com']
        self.assertEqual([e['host'] for e in self.fake.profile['include']], want)
        mac, ops = self.fake.profiles
        self.assertEqual([e['host'] for e in mac['include']], want)
        self.assertNotIn('include', ops)
        with mock.patch.object(cloudflare, 'api_for', return_value=self.fake):
            checks = {c[0]: c for c in cloudflare.client_only_checks(config.load(self.config_path))}
        self.assertTrue(checks['client-reauth'][1])

    def test_doctor_names_a_profile_that_cannot_re_authenticate(self):
        self.fake.profile = {'default': True, 'include': [{'host': 'example.cloudflareaccess.com'}]}
        with mock.patch.object(cloudflare, 'api_for', return_value=self.fake):
            checks = {c[0]: c for c in cloudflare.client_only_checks(config.load(self.config_path))}
        ok, message = checks['client-reauth'][1:3]
        self.assertFalse(ok)
        self.assertIn('default device profile is in Include mode without accounts.google.com', message)

    def test_someone_elses_route_for_our_name_stops_setup(self):
        self.fake.routes.append({'id': 'x', 'hostname': 'agents.example.com', 'tunnel_id': 'other', 'comment': 'prod'})
        with self.assertRaisesRegex(util.Failed, 'another tunnel'):
            self.run_setup()
        self.assertEqual(self.fake.routes[0]['id'], 'x')

    def test_pair_domain_is_refused(self):
        self.write(
            self.text.replace(
                'hub_domain = "agents-hub.example.com"',
                'hub_domain = "agents-hub.example.com"\npair_domain = "{id}-t3.example.com"',
            )
        )
        with self.assertRaisesRegex(util.Failed, 'pair_domain'):
            config.load(self.config_path)

    def test_the_tunnel_runs_next_to_the_edge_with_no_host_port_80(self):
        cfg = config.load(self.config_path)
        edge = render.edge_service(cfg)
        self.assertNotIn('80', [p.split(':')[-2] for p in edge['ports']])
        self.assertIn('--entrypoints.ingress.address=:80', edge['command'])
        self.assertEqual(edge['networks']['agentlab-edge']['ipv4_address'], render.EDGE_IP)
        self.assertEqual(
            edge['networks']['agentlab-edge']['aliases'], ['edge', 'agents.example.com', 'agents-hub.example.com']
        )
        tunnel = render.core(cfg)['services']['cloudflared']
        self.assertEqual(
            tunnel['extra_hosts'], [f'agents.example.com:{render.EDGE_IP}', f'agents-hub.example.com:{render.EDGE_IP}']
        )
        self.assertEqual(list(tunnel['networks']), ['agentlab-edge'])
        self.assertNotIn('ports', tunnel)
        self.assertIn('--token-file', tunnel['command'])

    def test_the_token_never_appears_in_the_compose_text(self):
        cfg = config.load(self.config_path)
        os.makedirs(f'{cfg["data"]}/secrets', exist_ok=True)
        with open(f'{cfg["data"]}/secrets/cloudflare-tunnel.token', 'w') as f:
            f.write('eyJ-secret-tunnel-token')
        text = render.all_files(cfg)['compose/agentlab-core/docker-compose.yml']
        self.assertNotIn('eyJ-secret-tunnel-token', text)
        self.assertNotIn('TUNNEL_TOKEN', text)

    def test_public_keeps_the_host_tunnel_and_loopback_ingress(self):
        public = resolve(PUBLIC)
        self.assertNotIn('cloudflared', render.core(public)['services'])
        self.assertEqual(render.edge_service(public)['networks']['agentlab-edge']['aliases'], ['edge'])
        self.assertIn('127.0.0.1:8088:8088', render.edge_service(public)['ports'])
        self.assertIn('--entrypoints.ingress.address=:8088', render.edge_service(public)['command'])

    def test_the_tunnel_container_gets_its_own_copy_of_the_token(self):
        cfg = config.load(self.config_path)
        with open(f'{cfg["data"]}/secrets/cloudflare-tunnel.token', 'w') as f:
            f.write('tok\n')
        with mock.patch.object(apply.os, 'chown') as chown:
            apply.tunnel_token_copy(cfg, util.Plan(False))
        dst = f'{cfg["data"]}/{render.TUNNEL_TOKEN_DIR}/token'
        with open(dst) as f:
            self.assertEqual(f.read(), 'tok')
        self.assertEqual(stat.S_IMODE(os.stat(dst).st_mode), 0o400)
        chown.assert_any_call(dst, render.CLOUDFLARED_UID, render.CLOUDFLARED_UID)

    def test_doctor_facts(self):
        self.run_setup()
        cfg = config.load(self.config_path)
        with mock.patch.object(cloudflare, 'api_for', return_value=self.fake):
            checks = {cid: ok for cid, ok, *_ in cloudflare.client_only_checks(cfg)}
        self.assertEqual(
            checks,
            {
                'gateway-proxy': True,
                'client-session': True,
                'client-reauth': True,
                'client-sign-in': True,
                'client-enrollment': True,
                'private-app': True,
                'hostname-routes': True,
                'no-public-dns': True,
            },
        )
        self.fake.settings = {'gateway_proxy_enabled': False}
        self.fake.dns.append({'id': 'x', 'name': 'agents.example.com', 'type': 'A', 'content': '1.2.3.4'})
        with mock.patch.object(cloudflare, 'api_for', return_value=self.fake):
            checks = {cid: ok for cid, ok, *_ in cloudflare.client_only_checks(cfg)}
        self.assertFalse(checks['gateway-proxy'])
        self.assertFalse(checks['no-public-dns'])

    def test_token_asks_for_the_routes_and_devices_permissions(self):
        keys = cloudflare.needed_permissions(config.load(self.config_path))
        self.assertIn('routes', keys)
        self.assertIn('devices', keys)
        self.assertNotIn('routes', cloudflare.needed_permissions(resolve(PUBLIC)))


class RequireWarp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = self.tmp.name
        os.makedirs(f'{d}/secrets')
        with open(f'{d}/secrets/cf.token', 'w') as f:
            f.write('api-token')
        self.config_path = f'{d}/cluster.toml'
        text = (
            PUBLIC.replace('data = "/srv/agentlab"', f'data = "{d}"').replace(
                'network = "public"', 'network = "public"\nrequire_warp = true'
            )
            + f'\n[cloudflare]\naccount_id = "acc"\nzone = "example.com"\napi_token_file = "{d}/secrets/cf.token"\n'
        )
        with open(self.config_path, 'w') as f:
            f.write(text)
        self.fake = FakeCloudflare()

    def run_setup(self):
        with (
            mock.patch.object(cloudflare, 'api_for', return_value=self.fake),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            cloudflare.setup(config.load(self.config_path), util.Plan(False), self.config_path)

    def test_policy_requires_the_gateway_check_and_the_app_takes_client_sessions(self):
        self.run_setup()
        (check,) = self.fake.posture
        self.assertEqual(check['type'], 'gateway')
        (people,) = self.fake.policies
        self.assertEqual(people['require'], [{'device_posture': {'integration_uid': check['id']}}])
        self.assertTrue(self.fake.apps[0]['allow_authenticate_via_warp'])
        self.assertTrue(self.fake.dns)

    def test_an_existing_gateway_check_is_reused_and_reruns_change_nothing(self):
        self.fake.posture.append({'id': 'gw', 'type': 'gateway', 'name': 'Gateway'})
        self.run_setup()
        self.assertEqual(len(self.fake.posture), 1)
        self.assertEqual(self.fake.policies[0]['require'], [{'device_posture': {'integration_uid': 'gw'}}])
        before = len(self.fake.writes)
        self.run_setup()
        self.assertEqual(self.fake.writes[before:], [])

    def test_require_warp_with_private_is_a_mistake(self):
        self.assertIn(
            'require_warp', problems(BASE.replace('team = "example"', 'team = "example"\nrequire_warp = true'))
        )


class RemoveNetwork(unittest.TestCase):
    def test_retries_while_a_stack_deleted_in_the_background_is_still_attached(self):
        answers = iter([(1, 'has active endpoints'), (0, '')])

        def fake(cmd, check=True):
            if cmd[:3] == ['docker', 'network', 'inspect']:
                return 0, json.dumps([{'Containers': {'abc': {}}}])
            if cmd[:3] == ['docker', 'network', 'rm']:
                return next(answers)
            return 0, ''

        with mock.patch.object(deploy, 'run', side_effect=fake) as run:
            deploy._disconnect_and_remove('agentlab-x', sleep=lambda s: None)
        rms = [c.args[0] for c in run.call_args_list if c.args[0][:3] == ['docker', 'network', 'rm']]
        self.assertEqual(len(rms), 2)


class HostsFile(unittest.TestCase):
    def test_block_is_added_replaced_and_removed_keeping_everything_else(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, 'hosts')
        with open(path, 'w') as f:
            f.write('127.0.0.1 localhost\n::1 localhost')
        names = ['agents.example.com', 'agents-hub.example.com']
        with contextlib.redirect_stdout(io.StringIO()):
            hostsfile.ensure(names, util.Plan(False), path)
            hostsfile.ensure(names, util.Plan(False), path)
        with open(path) as f:
            text = f.read()
        self.assertTrue(text.startswith('127.0.0.1 localhost\n::1 localhost\n'))
        self.assertEqual(text.count(hostsfile.BEGIN), 1)
        self.assertIn('127.0.0.1 agents-hub.example.com\n', text)
        with contextlib.redirect_stdout(io.StringIO()):
            hostsfile.ensure([], util.Plan(False), path)
        with open(path) as f:
            self.assertEqual(f.read(), '127.0.0.1 localhost\n::1 localhost\n')


class WslAutostart(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cfg = {'data': tmp.name, 'wsl_autostart': True}
        self.calls = []
        for p in (mock.patch.object(wslhost, 'is_wsl', return_value=True), mock.patch('os.access', return_value=True)):
            p.start()
            self.addCleanup(p.stop)

    def ensure(self, answer, env=None):
        def ps(command):
            self.calls.append(command)
            return 0, answer

        warned = []
        with (
            mock.patch.object(wslhost, 'ps', side_effect=ps),
            mock.patch.object(wslhost, 'warn', side_effect=warned.append),
            mock.patch.dict(os.environ, env or {}, clear=False),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            wslhost.ensure(self.cfg, util.Plan(False))
        return ' '.join(warned)

    def test_the_task_runs_the_loop_itself_for_this_distro(self):
        args = wslhost.arguments('Ubuntu-24.04')
        code = base64.b64decode(args.split()[-1]).decode('utf-16-le')
        self.assertTrue(code.startswith("$Distro = 'Ubuntu-24.04'\n"))
        self.assertIn('wsl.exe -d $Distro -u root --exec /bin/sleep infinity', code)
        self.assertNotIn('# ', code.splitlines()[1])

    def test_one_call_registers_it_and_the_distro_name_is_remembered_for_systemd_runs(self):
        self.ensure('boot', {'WSL_DISTRO_NAME': 'Ubuntu-24.04'})
        self.assertEqual(len(self.calls), 1)
        self.assertIn('-AtStartup', self.calls[0])
        with mock.patch.dict(os.environ, {'WSL_DISTRO_NAME': ''}):
            self.assertEqual(wslhost.distro(self.cfg), 'Ubuntu-24.04')

    def test_falling_back_to_sign_in_says_how_to_start_at_boot(self):
        self.assertIn('administrator', self.ensure('sign-in', {'WSL_DISTRO_NAME': 'Ubuntu'}))

    def test_without_a_distro_name_nothing_is_registered(self):
        with mock.patch.dict(os.environ, {'WSL_DISTRO_NAME': ''}):
            self.assertIn('from a WSL terminal', self.ensure('boot'))
        self.assertEqual(self.calls, [])

    def test_turned_off_removes_an_existing_task(self):
        self.cfg['wsl_autostart'] = False
        self.ensure('found')
        self.assertIn('Unregister-ScheduledTask', self.calls[-1])

    def test_not_wsl_does_nothing(self):
        with mock.patch.object(wslhost, 'is_wsl', return_value=False):
            self.ensure('boot', {'WSL_DISTRO_NAME': 'Ubuntu'})
        self.assertEqual(self.calls, [])


class SafeSwitch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = self.tmp.name
        os.makedirs(f'{d}/secrets')
        with open(f'{d}/secrets/cf.token', 'w') as f:
            f.write('api-token')
        self.config_path = f'{d}/cluster.toml'
        self.private = BASE.replace('data = "/srv/agentlab"', f'data = "{d}"') + (
            f'\n[cloudflare]\naccount_id = "acc"\nzone = "example.com"\napi_token_file = "{d}/secrets/cf.token"\n'
        )
        self.public = self.private.replace('team = "example"', 'team = "example"\nnetwork = "public"')
        self.fake = FakeCloudflare()
        self.go(self.public)
        self.fake.writes.clear()
        self.fake.calls.clear()

    def go(self, text, dry=False):
        with open(self.config_path, 'w') as f:
            f.write(text)
        with (
            mock.patch.object(cloudflare, 'api_for', return_value=self.fake),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            cloudflare.setup(config.load(self.config_path), util.Plan(dry), self.config_path)

    def public_still_works(self):
        conf = self.fake.configs['t1']['config']
        self.assertTrue(any(r.get('hostname') for r in conf['ingress']))
        self.assertTrue(self.fake.dns)

    def test_a_missing_permission_stops_before_any_change(self):
        self.fake.denied = {'/zerotrust/routes'}
        with self.assertRaises(util.Needs) as e:
            self.go(self.private)
        self.assertIn('Cloudflare One Networks', str(e.exception))
        self.assertIn('keeps working', str(e.exception))
        self.assertEqual(self.fake.writes, [])
        self.public_still_works()

    def test_the_dry_run_shows_the_same_gaps(self):
        self.fake.denied = {'/devices/settings'}
        with self.assertRaisesRegex(util.Needs, 'Zero Trust → Edit'):
            self.go(self.private, dry=True)
        self.assertEqual(self.fake.writes, [])

    def test_the_tokens_own_permissions_catch_a_read_only_grant(self):
        self.fake.own_groups = ['DNS Write', 'Access: Apps and Policies Write', 'Cloudflare One Connector Read']
        with self.assertRaisesRegex(util.Needs, 'can read but not change'):
            self.go(self.private)
        self.assertEqual(self.fake.writes, [])

    def test_a_refused_edit_mid_run_is_exit_2_and_leaves_public_working(self):
        self.fake.denied_writes = {'/zerotrust/routes'}
        with self.assertRaisesRegex(util.Needs, 'Cloudflare refused to route'):
            self.go(self.private)
        self.public_still_works()

    def test_gateway_proxy_off_is_turned_on_and_never_off(self):
        self.fake.settings = {'gateway_proxy_enabled': False, 'gateway_udp_proxy_enabled': False, 'other': 'kept'}
        self.go(self.private)
        self.assertEqual(
            self.fake.settings, {'gateway_proxy_enabled': True, 'gateway_udp_proxy_enabled': True, 'other': 'kept'}
        )
        before = len(self.fake.writes)
        self.go(self.private)
        self.assertNotIn(('PATCH', '/accounts/acc/devices/settings'), self.fake.writes[before:])

    def test_client_session_duration_is_set_only_while_it_has_none(self):
        self.fake.org = {'auth_domain': 'example.cloudflareaccess.com', 'name': 'netzero', 'created_at': 'x'}
        self.go(self.private)
        self.assertEqual(self.fake.org['warp_auth_session_duration'], '24h')
        self.assertEqual(self.fake.org['name'], 'netzero')
        self.assertNotIn('allow_authenticate_via_warp', self.fake.org)
        self.fake.org['warp_auth_session_duration'] = '8h'
        before = len(self.fake.writes)
        self.go(self.private)
        self.assertEqual(self.fake.org['warp_auth_session_duration'], '8h')
        self.assertNotIn('PUT', [m for m, p in self.fake.writes[before:] if p.endswith('/access/organizations')])

    def test_no_permission_to_set_it_stops_before_anything_else(self):
        self.fake.org.pop('warp_auth_session_duration')
        self.fake.denied_writes = {'/access/organizations'}
        with self.assertRaises(util.Needs) as e:
            self.go(self.private)
        self.assertIn('Access: Organizations → Edit', str(e.exception))
        self.assertEqual(self.fake.writes, [('PUT', '/accounts/acc/access/organizations')])
        self.public_still_works()

    def test_people_may_enroll_the_client_and_other_policies_stay(self):
        self.go(self.private)
        ours = next(p['id'] for p in self.fake.policies if p['name'] == 'agentlab-test')
        self.assertEqual(self.fake.enroll['policies'], [{'id': 'db', 'precedence': 1}, {'id': ours, 'precedence': 2}])
        self.assertEqual(self.fake.enroll['type'], 'warp')
        before = len(self.fake.writes)
        self.go(self.private)
        self.assertNotIn(('PUT', '/accounts/acc/access/apps/enroll'), self.fake.writes[before:])

    def test_cloudflares_12130_anyway_is_exit_2_not_a_failure(self):
        self.fake.org.pop('warp_auth_session_duration')
        with (
            mock.patch.object(cloudflare.Setup, 'preflight', return_value=[]),
            mock.patch.object(cloudflare.Setup, 'prerequisites'),
            self.assertRaises(util.Needs) as e,
        ):
            self.go(self.private)
        self.assertIn('session duration', str(e.exception))
        self.public_still_works()

    def test_an_account_that_allows_client_sign_in_everywhere_needs_no_per_app_flag(self):
        self.fake.org['allow_authenticate_via_warp'] = True
        self.fake.refuse_app_flag = True
        self.go(self.private)
        app = next(a for a in self.fake.apps if a['name'] == 'agentlab-test')
        self.assertFalse(app.get('allow_authenticate_via_warp'))
        with mock.patch.object(cloudflare, 'api_for', return_value=self.fake):
            checks = {c[0]: c[1] for c in cloudflare.client_only_checks(config.load(self.config_path))}
        self.assertTrue(checks['client-sign-in'])

    def test_a_private_app_sends_no_public_domain(self):
        self.go(self.private)
        app = next(a for a in self.fake.apps if a['name'] == 'agentlab-test')
        self.assertNotIn('domain', app)
        self.assertTrue(all(d['type'] == 'private' for d in app['destinations']))

    def test_an_invalid_request_is_not_mistaken_for_the_session_duration(self):
        e = cloudflare.ApiError('HTTP 400 [{"code": 12130, "message": "access.api.error.invalid_request: x"}]', 400)
        self.assertIsNone(cloudflare.refused(e, 'update Access application'))

    def test_a_refusal_shows_cloudflares_own_words(self):
        self.fake.refuse_app_flag = True
        with self.assertRaises(util.Needs) as e:
            self.go(self.private)
        self.assertIn('Cloudflare said:', str(e.exception))
        self.assertIn('12130', str(e.exception))

    def test_order_routes_and_app_before_the_switch_and_dns_last(self):
        self.go(self.private)
        writes = self.fake.writes
        route = next(i for i, (m, p) in enumerate(writes) if m == 'POST' and p.endswith('/routes/hostname'))
        app = next(i for i, (m, p) in enumerate(writes) if '/access/apps/' in p and m == 'PUT')
        switch = next(i for i, (m, p) in enumerate(writes) if p.endswith('/configurations'))
        dns = [i for i, (m, p) in enumerate(writes) if '/dns_records/' in p and m == 'DELETE']
        self.assertLess(route, switch)
        self.assertLess(app, switch)
        self.assertTrue(dns)
        self.assertGreater(min(dns), switch)

    def test_netzeros_half_switched_state_finishes_on_the_next_run(self):
        self.fake.configs['t1'] = {
            'config': {'ingress': [{'service': 'http_status:404'}], 'warp-routing': {'enabled': True}}
        }
        for host in ('agents.example.com', 'agents-hub.example.com'):
            self.fake.routes.append({'id': host, 'hostname': host, 'tunnel_id': 't1', 'comment': 'agentlab-test'})
        self.fake.dns.clear()
        self.fake.org.pop('warp_auth_session_duration')
        self.fake.denied_writes = {'/access/organizations'}
        with self.assertRaises(util.Needs) as e:
            self.go(self.private)
        self.assertIn('not reachable', str(e.exception))
        self.fake.denied_writes = set()
        self.go(self.private)
        app = next(a for a in self.fake.apps if a['name'] == 'agentlab-test')
        self.assertEqual({d['type'] for d in app['destinations']}, {'private'})
        self.assertTrue(app['allow_authenticate_via_warp'])
        self.assertEqual(self.fake.configs['t1']['config']['ingress'], [{'service': 'http_status:404'}])

    def test_back_to_public_makes_dns_first_and_drops_only_our_routes(self):
        self.go(self.private)
        self.fake.routes.append({'id': 'prod', 'hostname': 'db.example.com', 'tunnel_id': 'x', 'comment': 'prod'})
        self.fake.writes.clear()
        self.go(self.public)
        writes = self.fake.writes
        dns = next(i for i, (m, p) in enumerate(writes) if p.endswith('/dns_records') and m == 'POST')
        switch = next(i for i, (m, p) in enumerate(writes) if p.endswith('/configurations'))
        drop = [i for i, (m, p) in enumerate(writes) if '/routes/hostname/' in p and m == 'DELETE']
        self.assertLess(dns, switch)
        self.assertGreater(min(drop), switch)
        self.assertEqual([r['id'] for r in self.fake.routes], ['prod'])


class EnrollmentExposure(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = self.tmp.name
        os.makedirs(f'{d}/secrets')
        with open(f'{d}/secrets/cf.token', 'w') as f:
            f.write('api-token')
        self.config_path = f'{d}/cluster.toml'
        text = (
            BASE.replace('data = "/srv/agentlab"', f'data = "{d}"').replace(
                'admins = ["boss@example.com"]', 'admins = ["boss@example.com"]\nallow_domains = ["example.com"]'
            )
            + f'\n[cloudflare]\naccount_id = "acc"\nzone = "example.com"\napi_token_file = "{d}/secrets/cf.token"\n'
        )
        with open(self.config_path, 'w') as f:
            f.write(text)
        self.fake = FakeCloudflare()
        with (
            mock.patch.object(cloudflare, 'api_for', return_value=self.fake),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            cloudflare.setup(config.load(self.config_path), util.Plan(False), self.config_path)

    def checks(self):
        with mock.patch.object(cloudflare, 'api_for', return_value=self.fake):
            return {c[0]: c for c in cloudflare.client_only_checks(config.load(self.config_path))}

    def test_another_app_admitting_the_whole_domain_is_a_warning_and_untouched(self):
        self.fake.policies.append(
            {'id': 'dbp', 'name': 'DB everyone', 'include': [{'email_domain': {'domain': 'Example.com'}}]}
        )
        self.fake.apps.append({'id': 'db', 'name': 'company-db', 'policies': [{'id': 'dbp'}], 'destinations': []})
        self.fake.apps.append(
            {
                'id': 'pay',
                'name': 'payroll',
                'policies': [{'id': 'x', 'include': [{'email': {'email': 'a@example.com'}}]}],
            }
        )
        before = len(self.fake.writes)
        check = self.checks()['enrollment-exposure']
        self.assertEqual(check[4], 'warning')
        self.assertIn('company-db admits everyone @example.com', check[2])
        self.assertNotIn('payroll', check[2])
        self.assertNotIn('agentlab', check[2])
        self.assertEqual(len(self.fake.writes), before)

    def test_no_warning_when_other_apps_list_people(self):
        self.assertNotIn('enrollment-exposure', self.checks())

    def test_private_routes_without_an_app_are_an_info_line(self):
        self.fake.ip_routes = [
            {'network': '10.0.5.0/24', 'tunnel_name': 'prod'},
            {'network': '10.0.9.7/32', 'tunnel_name': 'prod'},
        ]
        self.fake.apps.append(
            {'id': 'db', 'name': 'db', 'policies': [], 'destinations': [{'type': 'private', 'cidr': '10.0.9.0/24'}]}
        )
        check = self.checks()['uncovered-routes']
        self.assertEqual(check[4], 'info')
        self.assertIn('10.0.5.0/24 (prod)', check[2])
        self.assertNotIn('10.0.9.7', check[2])


class HostTunnelCheck(unittest.TestCase):
    def checks(self, text):
        c = doctor.Checks()
        with mock.patch.object(doctor, '_active', return_value=False), mock.patch.object(doctor, '_domain_levels'):
            doctor._cloudflared(config.resolve(tomllib.loads(text)), c)
        return [i['id'] for i in c.items]

    def test_private_skips_the_host_service(self):
        self.assertNotIn('cloudflared', self.checks(BASE))

    def test_public_still_checks_it(self):
        public = BASE.replace('team = "example"', 'team = "example"\nnetwork = "public"')
        self.assertIn('cloudflared', self.checks(public))


HTTPS = BASE.replace('team = "example"', 'team = "example"\nhttps = true').replace(
    'hub_domain = "agents-hub.example.com"',
    'hub_domain = "agents-hub.example.com"\npair_domain = "{id}-t3.example.com"',
)


class PrivateHttps(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = self.d = self.tmp.name
        os.makedirs(f'{d}/secrets')
        with open(f'{d}/secrets/cf.token', 'w') as f:
            f.write('api-token')
        self.config_path = f'{d}/cluster.toml'
        self.text = HTTPS.replace('data = "/srv/agentlab"', f'data = "{d}"') + (
            f'\n[cloudflare]\naccount_id = "acc"\nzone = "example.com"\napi_token_file = "{d}/secrets/cf.token"\n'
        )
        self.write(self.text)
        self.fake = FakeCloudflare()
        self.cert = None  # None (nothing trusted yet) or the days the edge's certificate has left
        self.enterContext(mock.patch.object(cloudflare, 'edge_certificate', side_effect=lambda h: (self.cert, 'no')))
        self.enterContext(mock.patch.object(cloudflare, 'api_for', return_value=self.fake))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def write(self, text):
        with open(self.config_path, 'w') as f:
            f.write(text)

    def run_setup(self):
        cfg = config.load(self.config_path)
        cloudflare.setup(cfg, util.Plan(False), self.config_path)
        return cfg

    def finish(self):
        cfg = config.load(self.config_path)
        cloudflare.save_gate_secret(cfg, 'key', 'k' * 64)
        cloudflare.finish_https(cfg, util.Plan(False), wait=0)
        return cfg

    def people(self):
        return next(a for a in self.fake.apps if a['name'] == 'agentlab-test')

    def ports(self):
        return sorted((d['hostname'], d['port_range']) for d in self.people()['destinations'])

    def live(self):
        return os.path.exists(f'{self.d}/secrets/gate/https-live')

    def test_config_allows_pair_domain_only_with_https(self):
        self.assertEqual('', problems(HTTPS))
        self.assertIn('pair_domain', problems(HTTPS.replace('https = true', 'https = false')))
        self.assertIn('https must be true or false', problems(HTTPS.replace('https = true', 'https = "yes"')))
        public = PUBLIC.replace('network = "public"', 'network = "public"\nhttps = true')
        self.assertIn('https is for network = "private"', problems(public))
        cfg = resolve(HTTPS)
        self.assertTrue(config.private_https(cfg) and cfg['auth']['cloudflare']['https'])
        self.assertFalse(resolve(BASE)['auth']['cloudflare']['https'])

    def test_the_sign_in_app_and_its_client_come_first_then_port_80_only_until_the_certificate(self):
        self.run_setup()
        sign_in = next(a for a in self.fake.apps if a['name'] == 'agentlab-test sign-in')
        saas = sign_in['saas_app']
        self.assertEqual((sign_in['type'], saas['auth_type']), ('saas', 'oidc'))
        self.assertEqual(
            sorted(saas['redirect_uris']),
            [
                'https://agents-hub.example.com/_agentlab/oidc/callback',
                'https://agents.example.com/_agentlab/oidc/callback',
            ],
        )
        self.assertEqual(saas['scopes'], ['openid', 'email', 'profile'])
        self.assertEqual(saas['grant_types'], ['authorization_code_with_pkce'])
        self.assertEqual([p['id'] for p in sign_in['policies']], [p['id'] for p in self.people()['policies']])
        self.assertTrue(sign_in['allow_authenticate_via_warp'])
        folder = f'{self.d}/secrets/gate'
        with open(f'{folder}/oidc-client-id') as f:
            self.assertEqual(f.read(), saas['client_id'])
        with open(f'{folder}/oidc-client-secret') as f:
            self.assertEqual(f.read(), 'secret' + saas['client_id'][3:])
        self.assertEqual(stat.S_IMODE(os.stat(f'{folder}/oidc-client-secret').st_mode), 0o400)
        self.assertEqual(self.fake.apps.index(sign_in), 0)
        self.assertEqual({p for _, p in self.ports()}, {'80'})
        self.assertFalse(self.live())
        self.assertIn('sara-t3.example.com', [r['hostname'] for r in self.fake.routes])

    def test_port_443_and_the_redirect_once_the_certificate_is_trusted(self):
        self.run_setup()
        self.finish()
        self.assertEqual({p for _, p in self.ports()}, {'80'})
        self.assertFalse(self.live())
        self.cert = 89
        self.finish()
        self.assertEqual(
            self.ports(),
            [
                ('agents-hub.example.com', '443'),
                ('agents-hub.example.com', '80'),
                ('agents.example.com', '443'),
                ('agents.example.com', '80'),
                ('omar-t3.example.com', '443'),
                ('sara-t3.example.com', '443'),
            ],
        )
        self.assertTrue(self.live())
        before = len(self.fake.writes)
        self.cert = None
        self.run_setup()
        self.finish()
        self.assertEqual(self.fake.writes[before:], [])

    def test_a_lost_client_secret_means_a_new_client_and_the_old_one_goes(self):
        self.run_setup()
        self.fake.apps.append({'id': 'x', 'name': 'payroll', 'type': 'saas', 'saas_app': {'client_id': 'theirs'}})
        os.remove(f'{self.d}/secrets/gate/oidc-client-secret')
        self.run_setup()
        names = [(a['name'], (a.get('saas_app') or {}).get('client_id')) for a in self.fake.apps]
        self.assertIn(('payroll', 'theirs'), names)
        sign_ins = [cid for name, cid in names if name == 'agentlab-test sign-in']
        self.assertEqual(len(sign_ins), 1)
        self.assertNotEqual(sign_ins[0], 'cid1')
        with open(f'{self.d}/secrets/gate/oidc-client-id') as f:
            self.assertEqual(f.read(), sign_ins[0])

    def test_turning_https_off_goes_back_to_port_80_and_removes_only_agentlabs_sign_in(self):
        self.cert = 89
        self.run_setup()
        self.finish()
        self.assertTrue(self.live())
        self.fake.apps.append({'id': 'x', 'name': 'payroll', 'type': 'saas', 'saas_app': {'client_id': 'theirs'}})
        self.write(
            self.text.replace('https = true', 'https = false').replace('pair_domain = "{id}-t3.example.com"', '')
        )
        self.run_setup()
        self.assertEqual({p for _, p in self.ports()}, {'80'})
        self.assertEqual(sorted(a['name'] for a in self.fake.apps), ['agentlab-test', 'payroll'])
        self.assertFalse(self.live())

    def test_doctor_reports_the_https_pieces(self):
        cfg = self.run_setup()
        checks = {c[0]: c for c in cloudflare.client_only_checks(cfg)}
        self.assertFalse(checks['certificate-agents.example.com'][1])
        self.assertEqual(checks['certificate-agents.example.com'][4], 'error')
        self.assertTrue(checks['sign-in-app'][1])
        self.assertFalse(checks['https-port'][1])
        self.assertFalse(checks['gate-secrets'][1])
        self.cert = 5
        self.finish()
        checks = {c[0]: c for c in cloudflare.client_only_checks(cfg)}
        self.assertFalse(checks['certificate-agents.example.com'][1])
        self.assertEqual(checks['certificate-agents.example.com'][4], 'warning')
        self.assertTrue(checks['https-port'][1] and checks['gate-secrets'][1])
        with mock.patch.object(cloudflare, 'edge_redirect', return_value=(False, 'HTTP 404 without a redirect')):
            checks = {c[0]: c for c in cloudflare.client_only_checks(cfg)}
        self.assertFalse(checks['https-redirect-agents.example.com'][1])
        self.assertIn('404', checks['https-redirect-agents.example.com'][2])
        with mock.patch.object(cloudflare, 'edge_redirect', return_value=(True, '')):
            checks = {c[0]: c for c in cloudflare.client_only_checks(cfg)}
        self.assertTrue(checks['https-redirect-agents.example.com'][1])

    def test_plain_http_has_its_own_router_next_to_the_tls_one(self):
        dynamic = render.edge(resolve(HTTPS))
        routers = dynamic['http']['routers']
        self.assertEqual(routers['in-agent']['entryPoints'], ['websecure'])
        self.assertIn('tls', routers['in-agent'])
        self.assertEqual(routers['in-agent-http']['entryPoints'], ['ingress'])
        self.assertNotIn('tls', routers['in-agent-http'])
        self.assertEqual(routers['in-agent-http']['middlewares'], routers['in-agent']['middlewares'])

    def test_render_serves_443_with_a_dns_challenge_certificate_and_no_token_in_compose(self):
        cfg = resolve(HTTPS)
        edge = render.edge_service(cfg)
        self.assertIn('--entrypoints.websecure.address=:443', edge['command'])
        self.assertIn('--certificatesresolvers.le.acme.dnschallenge.provider=cloudflare', edge['command'])
        self.assertFalse([c for c in edge['command'] if 'httpchallenge' in c])
        self.assertEqual(edge['ports'], [f'127.0.0.1:{render.INGRESS_PORT}:80'])
        self.assertEqual(edge['environment'], {'CF_DNS_API_TOKEN_FILE': render.ACME_TOKEN})
        self.assertIn(f'/srv/agentlab/secrets/cloudflare-api.token:{render.ACME_TOKEN}:ro', edge['volumes'])
        self.assertIn('/srv/agentlab/edge-acme:/acme', edge['volumes'])
        self.assertIn('sara-t3.example.com', edge['networks']['agentlab-edge']['aliases'])
        routers = render.edge(cfg)['http']['routers']
        self.assertEqual(routers['in-agent']['entryPoints'], ['websecure'])
        self.assertEqual(routers['in-agent']['tls'], {'certResolver': 'le', 'domains': [{'main': '*.example.com'}]})
        self.assertEqual(routers['pair-sara']['entryPoints'], ['websecure'])
        self.assertNotIn('gate', routers['pair-sara']['middlewares'])
        forward = render.edge(cfg)['http']['middlewares']['gate']['forwardAuth']
        self.assertIn('X-Agentlab-Proof', forward['authResponseHeaders'])
        core = render.core(cfg)['services']
        self.assertIn(f'/srv/agentlab/secrets/gate:{render.GATE_SECRETS}:ro', core['gate']['volumes'])
        self.assertEqual(core['gate']['environment']['GATE_SECRETS'], render.GATE_SECRETS)
        self.assertIn('sara-t3.example.com:10.207.0.2', core['cloudflared']['extra_hosts'])

    def test_plain_private_renders_as_before(self):
        cfg = resolve(BASE)
        edge = render.edge_service(cfg)
        self.assertNotIn('--entrypoints.websecure.address=:443', edge['command'])
        self.assertNotIn('environment', edge)
        self.assertNotIn('tls', render.edge(cfg)['http']['routers']['in-agent'])
        self.assertNotIn('GATE_SECRETS', render.core(cfg)['services']['gate']['environment'])

    def test_setup_writes_https_and_the_t3_names_for_private(self):
        from agentlab import setup as guided  # noqa: PLC0415

        answers = {
            'reach': 'cloudflare',
            'admin': 'boss@example.com',
            'domain': 'agents.example.com',
            'hub_domain': 'agents-hub.example.com',
            'network': 'private',
            'https': True,
            'zone': 'example.com',
            'allow_domains': [],
            'agents': [('boss@example.com', 'boss')],
            'storage': 'shared',
            'android': False,
            'deploy': 'compose',
            'isolation': 'sysbox',
            'name': 'test',
            'tailscale': False,
        }
        cfg = config.resolve(tomllib.loads(guided.toml_text(answers)))
        self.assertTrue(config.private_https(cfg))
        self.assertEqual(cfg['agents'][0]['pair_host'], 'boss-t3.example.com')
