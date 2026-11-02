"""agentctl: config validation, the security-relevant shape of what it renders, cluster.toml edits, Cloudflare
setup against a fake API, and the agent-facing output contract (--json, exit codes)."""

import contextlib
import copy
import io
import json
import os
import re
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
    disks,
    doctor,
    init,
    install,
    main,
    privileges,
    render,
    tomledit,
    util,
    yaml,
)

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
        self.assertEqual('', problems(BASE.replace('team = "example"', 'team = ""')))  # cloudflare setup finds it
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
        self.assertIn('pair_domain', problems(cluster__pair_domain='t3.example.com'))
        cfg = resolve(cluster__pair_domain='{id}-t3.example.com')
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


class Migration(unittest.TestCase):
    """What moving an existing one-person setup in needs: a published hub, extra stacks, adopting signed-in agents."""

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
        self.assertFalse(config.ports_only(cfg))  # agents still go through the edge
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
        self.assertNotIn('volumes', render.core(resolve(self.ONE)))  # no named volume: state lives on the host
        cfg = resolve(self.ONE, hub__bark_url='http://host.docker.internal:7192/', hub__bark_public='http://phone:7192')
        hub = render.core(cfg)['services']['hub']
        self.assertEqual(hub['environment']['BARK_URL'], 'http://host.docker.internal:7192')
        self.assertEqual(hub['environment']['BARK_PUBLIC'], 'http://phone:7192')
        self.assertIn('host.docker.internal:host-gateway', hub['extra_hosts'])
        self.assertNotIn('bark', json.loads(config.to_json(cfg)))
        self.assertIn('bark_url', problems(self.ONE, hub__bark_url='host:7192'))

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
            with open(f'{d}/b/home/.claude.json', 'w') as f:  # Claude Code installed, nobody signed in
                f.write('{"numStartups": 1}')
            with (
                mock.patch('os.fchown'),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertTrue(apply.adopt(signed, util.Plan(False)))
                self.assertFalse(apply.adopt(signed, util.Plan(False)))  # once
                self.assertFalse(apply.adopt(fresh, util.Plan(False)))
            self.assertTrue(os.path.isfile(f'{d}/a/home/.config/agent/onboarded'))
            self.assertFalse(os.path.exists(f'{d}/b/home/.config'))
            with open(f'{d}/b/home/.claude.json', 'w') as f:
                f.write('{"oauthAccount": {"emailAddress": "sara@example.com"}}')
            self.assertTrue(apply.signed_in(f'{d}/b/home'))


class Rendering(unittest.TestCase):
    def setUp(self):
        self.cfg = resolve(
            cluster__pair_domain='{id}-t3.example.com', cluster__coolify_domain='agents-coolify.example.com'
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
        self.assertNotIn('middlewares', r)  # File Browser serves under its baseURL
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
        self.assertIn('"y": 1', yaml.dump({'y': 1}))  # a bare y key would read as true


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

    def test_set_key_keeps_the_comment(self):
        out = tomledit.set_key(self.TEXT, 'auth.cloudflare', 'audience', 'abc123')
        self.assertIn('audience = "abc123"                # filled in by setup', out)
        self.assertEqual(tomllib.loads(out)['auth']['cloudflare']['audience'], 'abc123')
        added = tomledit.set_key(self.TEXT, 'backups', 'keep_days', 7)
        self.assertEqual(tomllib.loads(added)['backups']['keep_days'], 7)


class FakeCloudflare:
    """Just enough of the Cloudflare API: tunnels, their config and token, DNS, Access policies, apps and IdPs."""

    def __init__(self):
        self.tunnels, self.configs, self.dns, self.policies, self.apps = [], {}, [], [], []
        self.idps = [
            {'id': 'g1', 'type': 'google-apps', 'name': 'Google Workspace'},
            {'id': 'o1', 'type': 'onetimepin', 'name': 'One-time PIN'},
        ]
        self.writes = []
        self.token = 'user'  # 'user' or 'account' token (they verify at different paths), or 'bad'
        self.denied = set()  # path fragments this token can't reach (the API answers 403)

    def call(self, method, path, body=None):
        if method != 'GET':
            self.writes.append((method, path))
        if any(d in path for d in self.denied):
            raise util.Failed(f'Cloudflare {method} {path}: HTTP 403 [{{"code": 10000}}]')
        if path.endswith('/tokens/verify'):
            if self.token == 'bad' or (self.token == 'user') != path.startswith('/user/'):
                raise util.Failed(f'Cloudflare GET {path}: HTTP 401')
            return {'status': 'active'}
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
                self.apps.append({**body, 'id': f'a{len(self.apps) + 1}', 'aud': f'aud{len(self.apps) + 1}'})
                return self.apps[-1]
            return copy.deepcopy(self.apps)
        if '/access/apps/' in path and method == 'PUT':
            app = next(a for a in self.apps if a['id'] == path.rsplit('/', 1)[1])
            app.update(body)
            return app
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
        text = BASE.replace('data = "/srv/agentlab"', f'data = "{d}"').replace(
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
        self.assertEqual(len(self.fake.writes), writes)  # re-sync keeps both: nothing to change

    def probe(self):
        cfg = config.load(self.config_path)
        with mock.patch.object(cloudflare, 'api_for', return_value=self.fake):
            return cloudflare.probe_token(cfg)

    def test_token_probes_report_what_it_lacks(self):
        self.assertEqual(dict(self.probe()), {'tunnels': True, 'dns': True, 'access': True, 'idps': True})
        self.fake.token = 'account'  # account-owned tokens verify under /accounts/<id>/
        self.assertTrue(all(ok for _, ok in self.probe()))
        for fragment, name in (
            ('/cfd_tunnel', 'tunnels'),
            ('/access/apps', 'access'),
            ('/identity_providers', 'idps'),
            ('/dns_records', 'dns'),
        ):
            self.fake.denied = {fragment}
            self.assertEqual([n for n, ok in self.probe() if not ok], [name])
        self.fake.denied = {'/zones'}  # the zone isn't in the token's scope at all
        self.assertEqual([n for n, ok in self.probe() if not ok], ['dns'])
        self.assertEqual(self.fake.writes, [])  # every probe is a read

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
    """Companions belong to their agent: the state file is the truth, cluster.toml only seeds it once."""

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
            self.companions.create(self.path, 'omar', 'three-c')  # seeded-bot counts too
        with open(self.path) as f:
            text = f.read().replace('max_per_agent = 2', 'max_per_agent = 0')
        with open(self.path, 'w') as f:
            f.write(text)
        self.companions.create(self.path, 'sara', 'three')  # 0 = no cap
        with open(self.path, 'w') as f:
            f.write(text.replace('max_per_agent = 0', 'max_per_agent = 0\nself_service = false'))
        with self.assertRaises(util.Needs):
            self.companions.create(self.path, 'omar', 'four')

    def test_only_the_companions_own_agent_removes_it_and_it_stays_removed(self):
        with self.assertRaisesRegex(util.Failed, 'has no companion'):
            self.companions.remove(self.path, 'sara', 'seeded-bot')
        os.makedirs(f'{self.tmp.name}/companions/seeded-bot')
        self.companions.remove(self.path, 'omar', 'seeded-bot')
        self.assertEqual(self.names(), [])  # still in cluster.toml, but already seeded: not brought back
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
        self.enterContext(mock.patch('agentlab.privileges.elevate'))  # Privileges below tests it on its own

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
            self.assertIn('id = "omar"', f.read())  # nothing changed

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


class Privileges(unittest.TestCase):
    """Host-changing commands re-run through sudo; agents (no TTY or --json) get exit 2 instead of a password prompt."""

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
            ['agent', 'remove', 'omar'],  # prints the plan and stops for --yes
            ['images', 'build'],  # this user reaches Docker
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
            # the check containers run as root and without sudo: pin both so only the refusal is under test
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
        self.groups['agentlab'].gr_gid = os.stat(self.etc).st_gid  # chown is mocked: line the group up with the file
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
