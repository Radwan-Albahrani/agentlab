"""Host services: throttle, watcher, janitor and install-step helpers."""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HOST = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix='agentlab-host-test-')
CLUSTER = os.path.join(TMP, 'rendered', 'cluster.json')
os.environ['AGENTLAB_CLUSTER'] = CLUSTER
sys.path.insert(0, HOST)
os.makedirs(os.path.dirname(CLUSTER), exist_ok=True)


def tearDownModule():  # TMP must exist before the imports read AGENTLAB_CLUSTER
    shutil.rmtree(TMP, ignore_errors=True)


def write_cluster(**extra):
    cfg = {
        'data': TMP,
        'agents': [
            {'id': 'sara', 'owner': 'sara@example.com', 'path': f'{TMP}/agents/sara', 'storage_unit': ''},
            {'id': 'omar', 'owner': 'omar@example.com', 'path': f'{TMP}/agents/omar', 'storage_unit': ''},
        ],
        'companions': [
            {'name': 'helper', 'agent': 'sara'},
            {'name': 'boss-bot', 'agent': 'omar'},
        ],
        'limits': {'throttle': {'io_psi_max': 25}},
        **extra,
    }
    with open(CLUSTER, 'w') as f:
        json.dump(cfg, f)
    for a in cfg['agents']:
        os.makedirs(f'{a["path"]}/home', exist_ok=True)
    return cfg


write_cluster()

import janitor.__main__ as janitor  # noqa: E402
import safe  # noqa: E402
from janitor.dedupe import dedupe  # noqa: E402
from throttle import scheduler, spool  # noqa: E402
from throttle.peaks import Peaks  # noqa: E402
from throttle.settings import ADMIT_GAP_S, DEFAULT_MB, IO_PRESSURE_MAX, MEMORY_PRESSURE_MAX, PEAK_MARGIN  # noqa: E402
from throttle.spool import Job  # noqa: E402
from watch import agent_requests, inventory, jobs, page_requests, secrets, storage, store  # noqa: E402

GB = 1024
POOL = (2 * GB, 15 * GB)
AGENTS = {'sara': (1 * GB, 12 * GB), 'omar': (1 * GB, 12 * GB)}
ME = os.getuid()


def job(agent, n, mb=2 * GB, *, admitted=False, known=True, signature=None, rss=0):
    return Job(
        agent,
        f'{agent}-{n}',
        signature or f'npm build {agent}-{n}',
        'npm',
        f'job {n}',
        created=n,
        seen=n,
        admitted=admitted,
        rss_mb=rss,
        estimate_mb=mb,
        known=known,
    )


def admit(jobs, pool=POOL, agents=AGENTS, memory=0, io=0, gap=ADMIT_GAP_S):
    return [j.id for j in scheduler.to_admit(jobs, pool, agents, memory, io, gap)]


class Throttle(unittest.TestCase):
    def test_oldest_job_starts_when_idle(self):
        self.assertEqual(admit([job('sara', 2), job('sara', 1)]), ['sara-1'])

    def test_one_start_at_a_time_and_spaced(self):
        running = job('omar', 0, admitted=True)
        self.assertEqual(admit([running, job('sara', 1)], gap=ADMIT_GAP_S - 1), [])
        self.assertEqual(admit([running, job('sara', 1)]), ['sara-1'])

    def test_disk_and_memory_pressure_hold_new_jobs(self):
        running = job('omar', 0, admitted=True)
        self.assertEqual(admit([running, job('sara', 1)], io=IO_PRESSURE_MAX + 1), [])
        self.assertEqual(admit([job('sara', 1)], io=IO_PRESSURE_MAX + 1), ['sara-1'])
        self.assertEqual(admit([running, job('sara', 1)], memory=MEMORY_PRESSURE_MAX + 1), [])
        self.assertEqual(admit([running, job('sara', 1)], memory=MEMORY_PRESSURE_MAX - 1), ['sara-1'])

    def test_pool_and_agent_room(self):
        running = job('omar', 0, 6 * GB, admitted=True)
        self.assertEqual(admit([running, job('sara', 1, 7 * GB)]), [])
        self.assertEqual(admit([running, job('sara', 1, 4 * GB)]), ['sara-1'])
        pool = (1 * GB, 30 * GB)
        self.assertEqual(admit([running, job('omar', 1, 6 * GB), job('sara', 2, 6 * GB)], pool=pool), ['sara-2'])

    def test_fair_and_learning_first(self):
        running = [job('sara', 0, 1 * GB, admitted=True), job('sara', 1, 1 * GB, admitted=True)]
        self.assertEqual(admit([*running, job('sara', 2, 1 * GB), job('omar', 3, 1 * GB)]), ['omar-3'])
        first = job('sara', 0, 1 * GB, admitted=True, known=False, signature='npm build x')
        self.assertEqual(admit([first, job('omar', 1, 1 * GB, known=False, signature='npm build x')]), [])

    def test_peaks(self):
        with (
            tempfile.TemporaryDirectory() as d,
            mock.patch('throttle.peaks.FILE', f'{d}/peaks.json'),
            mock.patch('throttle.peaks.STATE_DIR', d),
        ):
            peaks = Peaks()
            self.assertEqual(peaks.estimate_mb('x', 'npm'), DEFAULT_MB['npm'])
            peaks.record('x', 1000)
            peaks.record('x', 2000)
            self.assertEqual(Peaks().estimate_mb('x', 'npm'), round(2000 * PEAK_MARGIN))

    def test_spool_round_trip_from_cluster_json(self):
        homes = spool.agents()
        self.assertEqual(set(homes), {'sara', 'omar'})
        home = homes['sara']
        with mock.patch.object(safe, 'AGENT_UID', ME), mock.patch('safe.os.fchown'):
            spool.prepare(home)
            folder = os.path.join(home, spool.SPOOL)
            with open(f'{folder}/j1.job', 'w') as f:
                json.dump({'signature': 's', 'tool': 'npm', 'label': 'npm i', 'created': 1}, f)
            (found,) = spool.jobs('sara', home)
            self.assertFalse(found.admitted)
            spool.admit(home, found)
            self.assertTrue(spool.jobs('sara', home)[0].admitted)
            with open(f'{folder}/j1.done', 'w') as f:
                json.dump({'signature': 's', 'peak_mb': 900}, f)
            self.assertEqual(spool.finished(home), [('s', 900)])

    def test_spool_never_follows_an_agents_symlink(self):
        home = f'{TMP}/agents/omar/home'
        target = f'{TMP}/outside'
        os.makedirs(target, exist_ok=True)
        os.makedirs(f'{home}/.local/state', exist_ok=True)
        link = f'{home}/{spool.SPOOL}'
        if not os.path.islink(link):
            os.symlink(target, link)
        with self.assertRaises(OSError):
            spool.prepare(home)
        self.assertEqual(os.listdir(target), [])


class SafeFolder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = self.tmp.name
        p = mock.patch('safe.os.fchown')
        p.start()
        self.addCleanup(p.stop)

    def test_write_replaces_a_planted_symlink_instead_of_following_it(self):
        secret = os.path.join(self.home, 'host-file')
        with open(secret, 'w') as f:
            f.write('keep')
        with safe.Folder(self.home, 'box', create=True) as f:
            os.symlink(secret, os.path.join(self.home, 'box', 'status.json'))
            f.write('status.json', 'new')
        with open(secret) as f:
            self.assertEqual(f.read(), 'keep')
        self.assertFalse(os.path.islink(os.path.join(self.home, 'box', 'status.json')))

    def test_read_refuses_symlinks_and_fifos(self):
        with safe.Folder(self.home, 'box', create=True) as f:
            os.symlink('/etc/hostname', os.path.join(self.home, 'box', 'link'))
            os.mkfifo(os.path.join(self.home, 'box', 'pipe'))
            self.assertIsNone(f.read('link'))
            self.assertIsNone(f.read('pipe'))

    def test_dot_dot_is_refused(self):
        with self.assertRaises(ValueError):
            safe.Folder(self.home, '../x', create=True)


class Watch(unittest.TestCase):
    def test_alerts_fire_once_per_level_and_rearm(self):
        self.assertIsNone(storage.alert_change(79, 0))
        self.assertEqual(storage.alert_change(81, 0), ('up', 80))
        self.assertIsNone(storage.alert_change(85, 80))
        self.assertEqual(storage.alert_change(96, 80), ('up', 95))
        self.assertEqual(storage.alert_change(74, 80), ('down', 0))

    def test_breakdown(self):
        du = '300000000\t/p/sara/workspace\n5000\t/p/sara/tmp\n900000000\t/p/sara'
        rows = storage.breakdown(du, 'sara', '/p/sara')
        self.assertEqual([(r['path'], r['bytes']) for r in rows], [('workspace', 300000000), ('', 900000000)])
        self.assertEqual(rows[0]['agent'], 'sara')

    def test_storage_check_reports_every_agent(self):
        state = {}
        storage.check(state)
        usage = store.load('usage.json', {})
        self.assertEqual(set(usage['disks']), {'sara', 'omar'})
        self.assertIn('pool', usage)

    def test_secret_fingerprints_cover_subfolders(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(f'{d}/companions/helper')
            os.makedirs(f'{d}/.versions')
            for p in ('a.txt', 'companions/helper/bot-token.txt', '.versions/old'):
                with open(f'{d}/{p}', 'w') as f:
                    f.write(p)
            self.assertEqual(sorted(secrets.fingerprints(d)), ['a.txt', 'companions/helper/bot-token.txt'])

    def test_secret_rules_match_templates(self):
        rules = {'companions/{companion}/bot-token.txt': {'apply': [{'restart': 'companion-{companion}'}]}}
        _, names = secrets.match(rules, 'companions/helper/bot-token.txt')
        self.assertEqual(names, {'companion': 'helper'})
        self.assertEqual(secrets.match(rules, 'companions/helper/other.txt'), (None, {}))
        self.assertEqual(secrets.changes({}, {'a': '1'}), ([], []))

    def test_a_companion_secret_can_be_installed_in_its_agents_home(self):
        cfg = {'companions': [{'name': 'helper', 'agent': 'sara'}], 'agents': [{'id': 'sara', 'path': '/p/sara'}]}
        names = secrets.with_agent({'companion': 'helper'}, cfg)
        self.assertEqual(names['agent_home'], '/p/sara/home')
        self.assertEqual(secrets.with_agent({'companion': 'gone'}, cfg), {'companion': 'gone'})
        good, why = secrets.apply('x', {'copy': '{agent_home}/.config/agent/bridge-key'}, {'companion': 'gone'})
        self.assertFalse(good)
        self.assertIn('no place', why)

    def test_extra_secrets_apply_only_their_narrow_rules(self):
        home = f'{TMP}/agents/sara/home/.config'
        os.makedirs(home, exist_ok=True)
        with tempfile.TemporaryDirectory() as d:
            for f in ('media.txt', 'pass.txt', 'evil.txt'):
                with open(f'{d}/{f}', 'w') as fh:
                    fh.write('v1')
            rules = {
                'media.txt': {'apply': [{'restart': 'jellyfin'}, {'restart': 'coolify-'}]},
                'pass.txt': {'apply': [{'copy': f'{home}/pass-token'}]},
                'evil.txt': {'apply': [{'copy': '/etc/evil'}, {'redeploy': 'core'}]},
            }
            with open(f'{d}/map.json', 'w') as fh:
                json.dump(rules, fh)
            extra = {'folder': d, 'map': f'{d}/map.json'}
            events, restarted = [], []
            containers = {
                'items': [
                    {'name': 'jellyfin-abc', 'stack': 'media'},
                    {'name': 'coolify-proxy', 'stack': 'coolify'},
                ]
            }
            with (
                mock.patch.object(store, 'event', side_effect=lambda *a, **k: events.append(a)),
                mock.patch.object(store, 'load', return_value=containers),
                mock.patch.object(secrets.host, 'run', side_effect=lambda cmd: (restarted.append(cmd), (0, ''))[1]),
                mock.patch.object(secrets.os, 'chown'),
            ):
                state = {}
                secrets.check_extra(state, extra)
                self.assertEqual(events, [])
                for f in ('media.txt', 'pass.txt', 'evil.txt'):
                    with open(f'{d}/{f}', 'w') as fh:
                        fh.write('v2')
                secrets.check_extra(state, extra)
            by = {e[1].split()[0]: e for e in events}
            self.assertEqual(restarted, [['docker', 'restart', 'jellyfin-abc']])
            self.assertIn('✗ no container coolify-*', by['extra/media.txt'][2])
            with open(f'{home}/pass-token') as fh:
                self.assertEqual(fh.read(), 'v2')
            self.assertIn("not inside an agent's home", by['extra/evil.txt'][2])
            self.assertIn('not allowed for extra secrets', by['extra/evil.txt'][2])
            self.assertFalse(os.path.exists('/etc/evil'))

    def test_hub_requests(self):
        self.assertEqual(page_requests.parse('deploy~agentlab-agent-sara'), ('deploy', 'agentlab-agent-sara'))
        self.assertIsNone(page_requests.parse('format~disk'))
        known = {'hub-1': {'stack': 'agentlab-core'}, 'coolify-db': {'stack': 'coolify'}}
        self.assertTrue(page_requests.allowed('restart', 'hub-1', known))
        self.assertFalse(page_requests.allowed('restart', 'coolify-db', known))
        self.assertFalse(page_requests.allowed('deploy', '../../etc', known))
        self.assertTrue(page_requests.allowed('deploy', 'agentlab-core', known))

    def test_extra_stacks_are_shown_and_only_known_stacks_are_touched(self):
        lines = [
            json.dumps(
                {
                    'Names': 'jellyfin',
                    'Labels': 'com.docker.compose.project=media-jellyfin,com.docker.compose.service=jellyfin',
                    'State': 'running',
                }
            ),
            json.dumps({'Names': 'stray', 'Labels': '', 'State': 'running'}),
        ]
        rows = {r['name']: r for r in inventory.tag(lines, [], ['media-jellyfin'])}
        self.assertEqual(rows['jellyfin']['stack'], 'media-jellyfin')
        self.assertTrue(page_requests.allowed('restart', 'jellyfin', rows))
        self.assertFalse(page_requests.allowed('restart', 'stray', rows))
        self.assertFalse(page_requests.allowed('deploy', 'media-jellyfin', rows))

    def test_an_extra_stack_can_be_a_coolify_project(self):
        coolify = 'com.docker.compose.project={uuid},com.docker.compose.service={svc},coolify.projectName={project}'
        lines = [
            json.dumps({'Names': f'{svc}-x', 'Labels': coolify.format(uuid=u, svc=svc, project=p), 'State': 'running'})
            for u, svc, p in (('u1', 'jellyfin', 'media'), ('u2', 'sonarr', 'media'), ('u3', 'secret', 'other'))
        ]
        rows = {r['name']: r for r in inventory.tag(lines, [], ['media'])}
        self.assertEqual([rows[n]['stack'] for n in ('jellyfin-x', 'sonarr-x', 'secret-x')], ['media', 'media', ''])
        self.assertEqual(rows['jellyfin-x']['service'], 'jellyfin')
        self.assertTrue(page_requests.allowed('restart', 'sonarr-x', rows))
        self.assertFalse(page_requests.allowed('restart', 'secret-x', rows))

    def test_agents_are_kept_off_networks_coolify_adds(self):
        joined = {'agentlab-sara': {}, 'u1': {}, 'agentlab-omar': {}}
        self.assertEqual(inventory.extra_networks(joined, 'sara'), ['agentlab-omar', 'u1'])
        self.assertEqual(inventory.extra_networks({'agentlab-sara': {}}, 'sara'), [])
        calls = []

        def fake_run(cmd):
            calls.append(cmd)
            if cmd[1] == 'inspect':
                return 0, json.dumps({'agentlab-sara': {}, 'u1': {}})
            return 0, ''

        rows = [
            {'name': 'agent-u1', 'stack': 'agentlab-agent-sara', 'service': 'agent', 'state': 'running'},
            {'name': 'files-u1', 'stack': 'agentlab-agent-sara', 'service': 'files', 'state': 'running'},
        ]
        with mock.patch.object(inventory.host, 'run', fake_run), mock.patch.object(inventory.store, 'event') as event:
            inventory.keep_isolated(rows)
        self.assertEqual(
            [c for c in calls if c[1] == 'network'], [['docker', 'network', 'disconnect', 'u1', 'agent-u1']]
        )
        self.assertEqual(event.call_args.args[1], 'sara agent isolated again after a deploy')

    def test_inventory_tags_by_compose_project(self):
        stacks = [{'id': 'agentlab-core', 'uuid': ''}, {'id': 'agentlab-agent-sara', 'uuid': 'u1'}]
        lines = [
            json.dumps(
                {
                    'Names': 'edge-1',
                    'Labels': 'com.docker.compose.project=agentlab-core,com.docker.compose.service=edge',
                    'State': 'running',
                }
            ),
            json.dumps(
                {
                    'Names': 'agent-u1',
                    'Labels': 'com.docker.compose.project=u1,com.docker.compose.service=agent',
                    'State': 'running',
                }
            ),
            json.dumps({'Names': 'coolify-db', 'Labels': '', 'State': 'running'}),
            'not json',
        ]
        rows = inventory.tag(lines, stacks)
        self.assertEqual(
            [(r['service'], r['stack']) for r in rows],
            [('edge', 'agentlab-core'), ('agent', 'agentlab-agent-sara'), ('coolify-db', 'coolify')],
        )


class AgentRequests(unittest.TestCase):
    def setUp(self):
        self.cfg = write_cluster()
        self.calls = []
        for p in (
            mock.patch('safe.os.fchown'),
            mock.patch.object(agent_requests, 'DATA', TMP),
            mock.patch.object(agent_requests.host, 'run', side_effect=self.fake_run),
            mock.patch.object(agent_requests, 'companion_containers', return_value=['companion-x']),
        ):
            p.start()
            self.addCleanup(p.stop)
        self.events = []
        p = mock.patch.object(store, 'event', side_effect=lambda *a, **k: self.events.append(a))
        p.start()
        self.addCleanup(p.stop)

    def fake_run(self, cmd, timeout=120):
        self.calls.append(cmd)
        if 'agentctl' in ' '.join(cmd):
            return 0, json.dumps({'ok': True, 'error': '', 'messages': ['done']})
        return 0, ''

    def request(self, agent, filename, payload=None):
        folder = f'{TMP}/agents/{agent}/home/.agentlab/requests'
        os.makedirs(folder, exist_ok=True)
        with open(f'{folder}/{filename}', 'w') as f:
            f.write(json.dumps(payload) if payload is not None else '')
        agent_requests.handle_all()
        self.assertFalse(os.path.exists(f'{folder}/{filename}'), 'request files are deleted')
        with open(f'{TMP}/agents/{agent}/home/.agentlab/results/{filename}.json') as f:
            return json.load(f)

    def test_restart_own_companion(self):
        result = self.request('sara', 'restart~companion~helper')
        self.assertTrue(result['ok'], result)
        self.assertIn(['docker', 'restart', 'companion-x'], self.calls)

    def test_another_agents_companion_is_refused(self):
        result = self.request('sara', 'restart~companion~boss-bot')
        self.assertFalse(result['ok'])
        self.assertEqual(self.calls, [])

    def test_create_goes_through_agentctl_as_this_agent(self):
        result = self.request('sara', 'create~companion~new-bot', {'display_name': 'New', 'kind': 'slack'})
        self.assertTrue(result['ok'], result)
        cmd = self.calls[-1]
        self.assertEqual(cmd[cmd.index('create') : cmd.index('create') + 3], ['create', 'sara', 'new-bot'])

    def test_create_needs_a_json_object(self):
        folder = f'{TMP}/agents/sara/home/.agentlab/requests'
        os.makedirs(folder, exist_ok=True)
        with open(f'{folder}/create~companion~new-bot', 'w') as f:
            f.write('not json')
        agent_requests.handle_all()
        with open(f'{TMP}/agents/sara/home/.agentlab/results/create~companion~new-bot.json') as f:
            self.assertFalse(json.load(f)['ok'])

    def test_secret_is_written_and_never_echoed(self):
        value = 'xoxb-very-secret-value'
        result = self.request('sara', 'secret~companion~helper', {'key': 'bot-token.txt', 'value': value})
        self.assertTrue(result['ok'], result)
        path = f'{TMP}/secrets/companions/helper/bot-token.txt'
        with open(path) as f:
            self.assertEqual(f.read().strip(), value)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        self.assertNotIn(value, json.dumps(result))
        self.assertNotIn(value, json.dumps(self.events))

    def test_unknown_secret_key_and_oversized_payload(self):
        self.assertFalse(self.request('sara', 'secret~companion~helper', {'key': '../x', 'value': 'v'})['ok'])
        big = {'key': 'owner.txt', 'value': 'x' * (agent_requests.MAX_PAYLOAD + 10)}
        self.assertIn('larger than', self.request('sara', 'secret~companion~helper', big)['message'])

    def test_settings_merge(self):
        os.makedirs(f'{TMP}/companions/helper', exist_ok=True)
        with open(f'{TMP}/companions/helper/settings.json', 'w') as f:
            json.dump({'tone': 'calm', 'keep': 1}, f)
        self.assertTrue(self.request('sara', 'settings~companion~helper', {'tone': 'brief'})['ok'])
        with open(f'{TMP}/companions/helper/settings.json') as f:
            self.assertEqual(json.load(f), {'tone': 'brief', 'keep': 1})

    def test_bad_names_and_symlinks_are_ignored(self):
        folder = f'{TMP}/agents/omar/home/.agentlab/requests'
        os.makedirs(folder, exist_ok=True)
        os.symlink('/etc/hostname', f'{folder}/restart~companion~boss-bot')
        open(f'{folder}/rm~-rf~slash', 'w').close()
        agent_requests.handle_all()
        self.assertEqual(os.listdir(folder), [])
        self.assertEqual(self.calls, [])


class Dedupe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = self.tmp.name

    def put(self, rel, data, age=7200):
        p = os.path.join(self.ws, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f:
            f.write(data)
        t = time.time() - age
        os.utime(p, (t, t))
        return p

    def test_identical_package_files_across_worktrees_become_one(self):
        big = b'x' * 8192
        a = self.put('worktrees/app/t3-1/node_modules/react/index.js', big)
        b = self.put('worktrees/app/t3-2/node_modules/react/index.js', big)
        c = self.put('app/packages/ui/node_modules/react/index.js', big)
        other = self.put('worktrees/app/t3-2/node_modules/vue/index.js', b'y' * 8192)
        linked, freed = dedupe(self.ws)
        self.assertEqual((linked, freed), (2, 2 * 8192))
        self.assertEqual(len({os.stat(p).st_ino for p in (a, b, c)}), 1)
        self.assertNotEqual(os.stat(other).st_ino, os.stat(a).st_ino)
        self.assertEqual(dedupe(self.ws), (0, 0))

    def test_source_files_fresh_installs_and_dry_runs_are_left_alone(self):
        big = b'z' * 8192
        src = [self.put('worktrees/app/t3-1/src/data.json', big), self.put('worktrees/app/t3-2/src/data.json', big)]
        new = [
            self.put('worktrees/app/t3-1/node_modules/x/a.js', big, age=10),
            self.put('worktrees/app/t3-2/node_modules/x/a.js', big, age=10),
        ]
        old = [self.put('a/node_modules/y/b.js', big + b'1'), self.put('b/node_modules/y/b.js', big + b'1')]
        self.assertEqual(dedupe(self.ws, dry=True), (1, 8193))
        for pair in (src, new):
            self.assertNotEqual(os.stat(pair[0]).st_ino, os.stat(pair[1]).st_ino)
        self.assertNotEqual(os.stat(old[0]).st_ino, os.stat(old[1]).st_ino)


class Janitor(unittest.TestCase):
    def test_idle_worktrees(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(f'{root}/home/.t3/userdata')
            db = sqlite3.connect(f'{root}/home/.t3/userdata/statev2.sqlite')
            db.execute('create table orchestration_v2_projection_runs (thread_id, completed_at)')
            db.execute('create table orchestration_v2_projection_threads (thread_id, payload_json, deleted_at)')
            now = time.time()
            old = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now - 20 * 3600))
            fresh = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now - 3600))
            threads = (
                ('t1', 'done', old),
                ('t2', 'recent', fresh),
                ('t3', 'live', None),
                ('t4', 'delegated', None),
                ('t5', 'delegated-now', None),
            )
            for tid, wt, settled in threads:
                payload = {'worktreePath': f'/workspace/worktrees/app/{wt}', 'settledAt': settled}
                db.execute(
                    'insert into orchestration_v2_projection_threads values (?, ?, null)', (tid, json.dumps(payload))
                )
            db.executemany(
                'insert into orchestration_v2_projection_runs values (?, ?)',
                [('t3', None), ('t4', old), ('t4', old), ('t5', old), ('t5', fresh)],
            )
            db.commit()
            db.close()
            for wt in ('done', 'recent', 'live', 'orphan', 'delegated', 'delegated-now'):
                os.makedirs(f'{root}/workspace/worktrees/app/{wt}')
                open(f'{root}/workspace/worktrees/app/{wt}/.git', 'w').close()
            os.utime(f'{root}/workspace/worktrees/app/orphan', (now - 5 * 86400, now - 5 * 86400))
            self.assertEqual(
                janitor.idle_worktrees(root, now),
                [
                    '/workspace/worktrees/app/delegated',
                    '/workspace/worktrees/app/done',
                    '/workspace/worktrees/app/orphan',
                ],
            )


@unittest.skipUnless(shutil.which('git'), 'needs git')
def _read_json(path):
    with open(path) as f:
        return json.load(f)


def _write(path, text):
    with open(path, 'w') as f:
        f.write(text)


class Jobs(unittest.TestCase):
    def test_commands_are_checked_and_never_options(self):
        self.assertEqual(
            jobs.command('agent.add', {'id': 'lina', 'email': 'Lina@example.com', 'memory': '8g', 'cpus': '2'})[0],
            ['agent', 'add', 'lina', 'lina@example.com', '--memory', '8g', '--cpus', '2'],
        )
        self.assertEqual(
            jobs.command('agent.remove', {'id': 'lina', 'delete_data': True})[0], ['agent', 'remove', 'lina', '--yes']
        )
        self.assertEqual(
            jobs.command('agent.remove', {'id': 'lina', 'delete_data': 'yes'})[0],
            ['agent', 'remove', 'lina', '--keep-data'],
        )
        self.assertEqual(
            jobs.command('storage.set', {'person_size': 'auto', 'host_reserve': '15%'})[0],
            ['storage', 'set', '--person-size', 'auto', '--host-reserve', '15%'],
        )
        for op, args in (
            ('agent.add', {'id': '--yes', 'email': 'a@b.co'}),
            ('agent.add', {'id': 'ok', 'email': '-x@b.co --config=/etc/passwd'}),
            ('agent.set', {'id': 'ok', 'memory': '--force'}),
            ('agent.set', {'id': 'ok'}),
            ('storage.set', {'person_size': '1g; rm -rf /'}),
            ('shell', {}),
        ):
            with self.subTest(op=op, args=args), self.assertRaises(ValueError):
                jobs.command(op, args)

    def test_a_job_runs_in_its_own_unit_and_reports_its_exit(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        ran = []

        def run(cmd, timeout=120):
            ran.append(cmd)
            return 0, ''

        with (
            mock.patch.object(jobs.store, 'path', side_effect=lambda *p: os.path.join(tmp, *p)),
            mock.patch.object(jobs.store, 'load', side_effect=lambda n, d: _read_json(os.path.join(tmp, n))),
            mock.patch.object(
                jobs.store, 'dump', side_effect=lambda n, d: json.dump(d, open(os.path.join(tmp, n), 'w'))
            ),
            mock.patch.object(jobs.store, 'event'),
            mock.patch.object(jobs.host, 'run', side_effect=run),
            mock.patch.object(jobs.host, 'unit_active', return_value=True),
        ):
            os.makedirs(f'{tmp}/jobs/queue')
            for n, args in enumerate(({'id': 'lina', 'email': 'lina@example.com'}, {'id': 'omar'})):
                job = {'id': f'170000000{n}-0000000{n}', 'op': 'agent.add' if n == 0 else 'agent.set', 'args': args}
                _write(f'{tmp}/jobs/queue/{job["id"]}.json', json.dumps(job))
            jobs.tick()
            self.assertEqual(ran[0][:3], ['systemd-run', '--unit', 'agentlab-job-1700000000-00000000'])
            self.assertEqual(ran[0][-4:], ['agent', 'add', 'lina', 'lina@example.com'])
            jobs.tick()  # one at a time: the second waits
            self.assertEqual(len(ran), 1)
            with open(f'{tmp}/jobs/1700000000-00000000.log', 'a') as f:
                f.write('  deploy agentlab-agent-lina\n! Cloudflare was not updated\n')
            _write(f'{tmp}/jobs/1700000000-00000000.rc', '0\n')
            jobs.tick()
            first = _read_json(f'{tmp}/jobs/1700000000-00000000.json')
            self.assertEqual((first['state'], first['message']), ('done', 'Cloudflare was not updated'))
            second = _read_json(f'{tmp}/jobs/1700000001-00000001.json')
            self.assertEqual((second['state'], second['message']), ('failed', 'nothing to change'))


class Trim(unittest.TestCase):
    def test_each_mounted_disk_is_trimmed_once(self):
        cfg = {
            'agents': [
                {'id': 'a', 'storage_unit': '/p/sara'},
                {'id': 'b', 'storage_unit': '/p/sara'},
                {'id': 'c', 'storage_unit': '/p/omar'},
                {'id': 'd', 'storage_unit': ''},
            ]
        }
        with (
            mock.patch.object(janitor.os.path, 'ismount', side_effect=lambda p: p == '/p/sara'),
            mock.patch.object(janitor, '_run', return_value='/p/sara: 3 GiB trimmed') as ran,
            mock.patch.object(janitor, 'DRY', False),
        ):
            self.assertEqual(janitor.trim(cfg), ['/p/sara: 3 GiB trimmed'])
        ran.assert_called_once_with(['fstrim', '-v', '/p/sara'])


class WorktreeNotice(unittest.TestCase):
    def git(self, *args, cwd=None):
        env = {
            **os.environ,
            'GIT_AUTHOR_NAME': 'a',
            'GIT_AUTHOR_EMAIL': 'a@x',
            'GIT_COMMITTER_NAME': 'a',
            'GIT_COMMITTER_EMAIL': 'a@x',
            'GIT_AUTHOR_DATE': self.old_date,
            'GIT_COMMITTER_DATE': self.old_date,
        }
        return subprocess.run(['git', *args], cwd=cwd or self.repo, env=env, check=True, capture_output=True, text=True)

    def test_unsaved_work_is_kept_until_the_notice_ends_then_saved_and_removed(self):
        tmp = tempfile.mkdtemp(dir=TMP)
        old = time.time() - 10 * 86400
        self.old_date = f'{int(old)} +0000'
        self.repo = f'{tmp}/repo'
        subprocess.run(['git', 'init', '-q', '--bare', f'{tmp}/origin.git'], check=True)
        subprocess.run(['git', 'clone', '-q', f'{tmp}/origin.git', self.repo], check=True, capture_output=True)
        self.git('commit', '-q', '--allow-empty', '-m', 'base')
        self.git('push', '-q', 'origin', 'HEAD')
        trees = {}
        for name in ('clean', 'stale', 'fresh'):
            trees[name] = f'{tmp}/wt/{name}'
            self.git('worktree', 'add', '-q', '-b', name, trees[name])
        for name, when in (('stale', old), ('fresh', time.time())):
            path = f'{trees[name]}/notes.txt'
            with open(path, 'w') as f:
                f.write(name)
            os.utime(path, (when, when))
        out = subprocess.run(
            ['bash', '-c', janitor.REMOVE_WORKTREES],
            input=''.join(f'{t}\n' for t in trees.values()),
            env={
                **os.environ,
                'NOTICE_DAYS': '7',
                'DRY': '',
                'GIT_AUTHOR_NAME': 'a',
                'GIT_AUTHOR_EMAIL': 'a@x',
                'GIT_COMMITTER_NAME': 'a',
                'GIT_COMMITTER_EMAIL': 'a@x',
            },
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        self.assertFalse(os.path.exists(trees['clean']))
        self.assertFalse(os.path.exists(trees['stale']))
        self.assertTrue(os.path.exists(trees['fresh']))
        self.assertIn('fresh (1 uncommitted; removed ', out)
        ref = 'refs/agentlab/removed/' + trees['stale'].replace('/', '-')
        self.assertIn(f'saved as {ref}', out)
        self.assertEqual(self.git('show', f'{ref}:notes.txt').stdout, 'stale')


class PickPackage(unittest.TestCase):
    """pick_package under pipefail with an apt-cache that keeps writing after the Candidate line (#17)."""

    def pick(self, policy):
        tmp = tempfile.mkdtemp(dir=TMP)
        fake = os.path.join(tmp, 'apt-cache')
        with open(fake, 'w') as f:
            f.write('#!/bin/bash\ncase "$2" in\n')
            for pkg, candidate in policy.items():
                f.write(f'  {pkg}) echo "{pkg}:"; echo "  Candidate: {candidate}"; seq 1 200000;;\n')
            f.write('esac\n')
        os.chmod(fake, 0o755)
        lib = os.path.join(HOST, 'install', 'lib.sh')
        # ls() stubbed so no apt-get update runs
        cmd = f'source "{lib}"; ls() {{ :; }}; pick_package openjdk-21-jre-headless openjdk-25-jre-headless openjdk-17-jre-headless'
        return subprocess.run(
            ['bash', '-c', cmd],
            capture_output=True,
            text=True,
            env={**os.environ, 'PATH': f'{tmp}:{os.environ["PATH"]}'},
            check=False,
        )

    def test_finds_the_first_available_despite_a_long_policy(self):
        for _ in range(5):  # the old bug was timing-dependent
            out = self.pick({'openjdk-21-jre-headless': '21.0.13+9-1~deb13u2', 'openjdk-25-jre-headless': '25.0.5'})
            self.assertEqual((out.returncode, out.stdout.strip()), (0, 'openjdk-21-jre-headless'))

    def test_skips_packages_without_a_candidate(self):
        out = self.pick({'openjdk-21-jre-headless': '(none)', 'openjdk-25-jre-headless': '25.0.5+8-1~deb13u1'})
        self.assertEqual(out.stdout.strip(), 'openjdk-25-jre-headless')

    def test_none_available(self):
        self.assertEqual(self.pick({'openjdk-21-jre-headless': '(none)'}).returncode, 1)


class HostTunnel(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(dir=TMP)
        self.calls = os.path.join(self.dir, 'calls')
        bin_dir = os.path.join(self.dir, 'bin')
        os.makedirs(bin_dir)
        with open(os.path.join(bin_dir, 'systemctl'), 'w') as f:
            f.write(f'#!/bin/sh\necho "systemctl $*" >> {self.calls}\nexit 0\n')
        os.chmod(os.path.join(bin_dir, 'systemctl'), 0o755)
        self.path = f'{bin_dir}:{os.environ["PATH"]}'
        self.unit = os.path.join(self.dir, 'cloudflared.service')

    def retire(self, unit_text):
        with open(self.unit, 'w') as f:
            f.write(unit_text)
        script = os.path.join(HOST, 'install', '40-cloudflared.sh')
        out = subprocess.run(
            ['bash', '-c', f'source "{script}" && retire_host_tunnel "{self.unit}"'],
            capture_output=True,
            text=True,
            env={**os.environ, 'PATH': self.path},
            check=True,
        )
        if not os.path.exists(self.calls):
            return out.stdout, []
        with open(self.calls) as f:
            return out.stdout, f.read().splitlines()

    def test_ours_stops(self):
        out, calls = self.retire(
            'ExecStart=/bin/sh -c \'TUNNEL_TOKEN="$(cat /srv/agentlab/secrets/cloudflare-tunnel.token)" exec x\''
        )
        self.assertIn('systemctl disable -q --now cloudflared', calls)
        self.assertIn('host cloudflared stopped', out)

    def test_someone_elses_stays(self):
        out, calls = self.retire('ExecStart=/usr/bin/cloudflared tunnel run --token-file /etc/other/token')
        self.assertEqual([c for c in calls if 'disable' in c], [])
        self.assertEqual(out, '')


class SysboxInstall(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(dir=TMP)
        self.calls = os.path.join(self.dir, 'calls')
        bin_dir = os.path.join(self.dir, 'bin')
        os.makedirs(bin_dir)
        with open(os.path.join(bin_dir, 'systemctl'), 'w') as f:
            f.write(f'#!/bin/sh\necho "systemctl $*" >> {self.calls}\n')
        os.chmod(os.path.join(bin_dir, 'systemctl'), 0o755)
        self.path = f'{bin_dir}:{os.environ["PATH"]}'
        self.dropin = os.path.join(self.dir, 'sysbox-mgr.service.d', 'agentlab.conf')
        os.makedirs(os.path.dirname(self.dropin))

    def remove(self):
        script = os.path.join(HOST, 'install', '20-sysbox.sh')
        out = subprocess.run(
            ['bash', '-c', f'source "{script}" && remove_old_dropin "{self.dropin}"'],
            capture_output=True,
            text=True,
            env={**os.environ, 'PATH': self.path},
            check=True,
        )
        if not os.path.exists(self.calls):
            return out.stdout, []
        with open(self.calls) as f:
            return out.stdout, f.read().splitlines()

    def test_the_old_drop_in_goes_and_sysbox_restarts(self):
        with open(self.dropin, 'w') as f:
            f.write('[Service]\nExecStart=\nExecStart=/usr/bin/sysbox-mgr --subid-range-size 262144\n')
        out, calls = self.remove()
        self.assertFalse(os.path.exists(self.dropin))
        self.assertFalse(os.path.exists(os.path.dirname(self.dropin)))
        self.assertEqual(calls, ['systemctl daemon-reload', 'systemctl restart sysbox'])
        self.assertIn('removed', out)

    def test_someone_elses_drop_in_stays(self):
        with open(self.dropin, 'w') as f:
            f.write('[Service]\nEnvironment=FOO=1\n')
        out, calls = self.remove()
        self.assertTrue(os.path.exists(self.dropin))
        self.assertEqual((out, calls), ('', []))

    def test_nothing_to_do_without_one(self):
        self.assertEqual(self.remove(), ('', []))

    def test_no_sysbox_mgr_options_are_written(self):
        with open(os.path.join(HOST, 'install', '20-sysbox.sh')) as f:
            text = f.read()
        self.assertNotIn('ExecStart=', text)


if __name__ == '__main__':
    unittest.main()
