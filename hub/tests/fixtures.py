"""Example on-disk data for the hub's tests and throwaway instance: python3 fixtures.py <folder> (wipes it first)."""

import json
import os
import shutil
import sqlite3
import sys
import time

AGENTS = ('admin', 'sara', 'lab')
OWNER = {'admin': 'admin@example.com', 'sara': 'sara@example.com', 'lab': 'sara@example.com'}
COMPANION = 'scout'  # admin's; OTHER is sara's
OTHER = 'helper'
GB = 2**30
NOW = time.time()


def cluster(root):
    return {
        'name': 'example',
        'domain': 'agents.example.com',
        'hub_domain': 'agents-hub.example.com',
        'coolify_domain': '',
        'pair_domain': '{id}-t3.example.com',
        'timezone': 'UTC',
        'data': '/srv/agentlab',
        'deploy': 'compose',
        'isolation': 'sysbox',
        'auth': {
            'mode': 'none',
            'ingress': 'loopback',
            'admins': ['admin@example.com'],
            'cloudflare': {'team': 'example', 'audience': ''},
        },
        'agents': [
            {
                'id': a,
                'owner': OWNER[a],
                'path': f'/srv/agentlab/agents/{a}',
                'memory': '12g',
                'cpus': 4,
                'disk': '60G',
                'upstream': f'http://agent-{a}',
                'pair_host': f'{a}-t3.example.com' if a == 'admin' else '',
                'color': 'green' if a == 'sara' else '',
            }
            for a in AGENTS
        ],
        'limits': {'total_memory': '96g', 'throttle': {'agent_gb': 12, 'pool_gb': 96, 'io_psi_max': 25}},
        'android': {'enabled': True},
        'backups': {'keep_days': 14, 'time': '03:30'},
        'storage': {'mode': 'per-person', 'pool_size': '', 'person_size': '60G'},
        'hub': {'extra_stacks': ['media']},
        'companions': [
            {'name': COMPANION, 'display_name': 'Scout', 'agent': 'admin', 'kind': 'slack'},
            {'name': OTHER, 'display_name': 'Helper', 'agent': 'sara', 'kind': 'slack'},
        ],
    }


def dump(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=1)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)


def container(name, service, stack, state='running', status='Up 2 hours (healthy)'):
    return {'name': name, 'service': service, 'stack': stack, 'state': state, 'status': status, 'image': 'example'}


def watch(root):
    disk = {'size': 60 * GB, 'used': 21 * GB, 'avail': 39 * GB}
    dump(
        f'{root}/watch/usage.json',
        {
            'at': NOW,
            'pool': {'size': 512 * GB, 'used': 140 * GB, 'avail': 372 * GB},
            'people': {
                'admin@example.com': disk,
                'sara@example.com': {'size': 60 * GB, 'used': 50 * GB, 'avail': 10 * GB},
            },
            'scan': {
                'at': NOW - 600,
                'took': 41,
                'items': [
                    {'agent': 'admin', 'path': '', 'bytes': 21 * GB},
                    {'agent': 'admin', 'path': 'home', 'bytes': 12 * GB},
                    {'agent': 'admin', 'path': 'workspace', 'bytes': 9 * GB},
                    {'agent': 'admin', 'path': 'home/.cache', 'bytes': 6 * GB},
                    {'agent': 'admin', 'path': 'workspace/app', 'bytes': 8 * GB},
                ],
            },
        },
    )
    items = [
        container('edge', 'edge', 'agentlab-core'),
        container('gate', 'gate', 'agentlab-core'),
        container('hub', 'hub', 'agentlab-core'),
        container('agent-admin', 'agent', 'agentlab-agent-admin'),
        container('agent-sara', 'agent', 'agentlab-agent-sara'),
        container('agent-lab', 'agent', 'agentlab-agent-lab'),
        container(f'companion-{COMPANION}', 'companion', f'agentlab-companion-{COMPANION}'),
        container(f'companion-{OTHER}', 'companion', f'agentlab-companion-{OTHER}'),
        container('media-jellyfin-1', 'jellyfin', 'media'),
        container('stray-1', 'stray', 'someone-elses-project'),
    ]
    dump(f'{root}/watch/containers.json', {'at': NOW, 'items': items, 'stacks': []})
    events = [
        {'at': NOW - 3600, 'kind': 'cleanup', 'title': 'Nightly cleanup', 'detail': 'freed 2.1 GB', 'ok': True},
        {'at': NOW - 1800, 'kind': 'deploy', 'title': 'agentlab-core deployed', 'detail': '', 'ok': True},
        {'at': NOW - 60, 'kind': 'secret', 'title': 'coolify.token changed', 'detail': 'read when used', 'ok': True},
    ]
    write(f'{root}/watch/events.jsonl', ''.join(json.dumps(e) + '\n' for e in events))
    os.makedirs(f'{root}/watch/requests', exist_ok=True)


def rendered(root):
    dump(f'{root}/cluster.json', cluster(root))
    stacks = {'agentlab-core': 'edge', **{f'agentlab-agent-{a}': 'agent' for a in AGENTS}}
    stacks[f'agentlab-companion-{COMPANION}'] = 'companion'
    stacks[f'agentlab-companion-{OTHER}'] = 'companion'
    for sid, service in stacks.items():
        write(
            f'{root}/rendered/compose/{sid}/docker-compose.yml',
            f'# Rendered by agentctl from /etc/agentlab/cluster.toml: edit that, then `agentctl apply`.\n'
            f'services:\n  {service}:\n    image: agentlab/{service}:latest\n    restart: unless-stopped\n',
        )


def secrets(root):
    for name, text in {
        'coolify.token': 'example-token\n',
        'cloudflare-api.token': 'example-token\n',
        f'companions/{COMPANION}/bot-token.txt': 'xoxb-example\n',
        f'companions/{COMPANION}/owner.txt': 'U0EXAMPLE\n',
        f'companions/{OTHER}/owner.txt': 'U0SARA\n',
        f'companions/{COMPANION}/github-app-key.pem': '-----BEGIN RSA PRIVATE KEY-----\nexample\n',
        'unmapped-note.txt': 'something\n',
    }.items():
        write(f'{root}/secrets/{name}', text)


def companion_db(path):
    con = sqlite3.connect(path)
    con.executescript(
        """
create table events (id integer primary key, at real not null, kind text, title text, task text, "to" text,
                     detail text, ok integer not null default 1);
create table tasks (id text primary key, title text, kind text, requester text, status text, waiting text,
                    outcome text, started text, ended text, thread text, slack text, source text, updated real);
create table polls (id text primary key, task text, open integer, closes real, data text, updated real);
create table pulls (id text primary key, repo text, number integer, updated text, data text);
"""
    )
    iso = lambda t: time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(t))  # noqa: E731
    slack = 'https://example.slack.com/archives/C0EXAMPLE/p1'
    tasks = [
        ('t1', 'Draft the release notes', 'task', 'Sara', 'waiting', 'approval', '', iso(NOW - 900), '', 'th1', slack),
        ('t2', 'Summarise the incident thread', 'task', 'Sara', 'working', '', '', iso(NOW - 300), '', 'th2', slack),
        (
            't3',
            'Book the meeting room',
            'errand',
            'Admin',
            'done',
            '',
            'Booked.',
            iso(NOW - 7200),
            iso(NOW - 7000),
            '',
            slack,
        ),
        (
            't4',
            'Review example/app#12',
            'review',
            'Admin',
            'done',
            '',
            '2 findings',
            iso(NOW - 5000),
            iso(NOW - 4000),
            'th4',
            '',
        ),
    ]
    con.executemany('insert into tasks values (?,?,?,?,?,?,?,?,?,?,?,"slack",?)', [(*t, NOW) for t in tasks])
    events = [
        (NOW - 7000, 'sent', 'Booked the meeting room', 't3', '#general', 'Room 2, 10:00', 1),
        (NOW - 3000, 'files', 'Shared the report', 't2', 'Sara', 'report.pdf', 1),
        (NOW - 120, 'task', 'New task from Sara', 't2', '', '', 1),
    ]
    con.executemany('insert into events (at, kind, title, task, "to", detail, ok) values (?,?,?,?,?,?,?)', events)
    poll = {
        'question': 'Lunch on Thursday?',
        'channel': 'general',
        'link': slack,
        'multiple': False,
        'closed': None,
        'options': [
            {'label': 'Pizza', 'votes': 2, 'voters': [{'name': 'Sara', 'avatar': ''}, {'name': 'Admin', 'avatar': ''}]},
            {'label': 'Salad', 'votes': 0, 'voters': []},
        ],
    }
    con.execute('insert into polls values (?,?,?,?,?,?)', ('p1', 't1', 1, NOW + 86400, json.dumps(poll), NOW))
    pull = {
        'title': 'Add the export button',
        'url': 'https://github.com/example/app/pull/12',
        'draft': False,
        'author': 'example-admin',
        'avatar': '',
        'labels': [{'name': 'feature', 'color': '0e8a16'}],
        'additions': 120,
        'deletions': 8,
        'created': iso(NOW - 86400),
        'updated': iso(NOW - 3600),
        'head': 'abc1234',
        'ci': 'passing',
        'review': {
            'status': 'done',
            'outcome': '2 findings · QA verified',
            'task': 't4',
            'head': 'abc1234',
            'at': iso(NOW - 4000),
            'counts': {'findings': 2, 'blocking': 0, 'open': 0, 'qa': 'pass'},
            'run': {'n': 1, 'of': 3, 'done': True},
        },
    }
    # #12 is done; #13 and #14 were asked for with it and are still going (a review batch)
    reviewing = {'status': 'working', 'outcome': '', 'task': 't5', 'head': '', 'at': iso(NOW - 600)}
    queued = {'status': 'queued', 'outcome': 'Waiting for a free slot', 'task': '', 'head': '', 'at': ''}
    for number, title, hours, review in (
        (12, pull['title'], 1, pull['review']),
        (13, 'Fix the date picker on Safari', 2, dict(reviewing, run={'n': 2, 'of': 3, 'done': False})),
        (14, 'Bump the API client', 3, dict(queued, run={'n': 3, 'of': 3, 'done': False})),
        # the worst case for a narrow screen: a long title, labels, a blocking result and new commits since
        (
            15,
            'refactor(api): reduce migration-inputs to the tenantless ops grants, one role-default entry per role, '
            'revoke and stop lists and one pure migratedAdditionsFor [ENG-6025]',
            4,
            {
                'status': 'done',
                'outcome': '2 findings (1 blocking) · QA partly verified',
                'task': 't6',
                'head': 'old1234',
                'at': iso(NOW - 5000),
                'counts': {'findings': 2, 'blocking': 1, 'open': 0, 'qa': 'partial'},
            },
        ),
    ):
        p = dict(pull, title=title, url=f'https://github.com/example/app/pull/{number}', review=review)
        if number == 14:
            p['draft'] = True
        if number == 15:
            p['labels'] = [{'name': 'lane:red', 'color': 'd73a4a'}, {'name': 'agent', 'color': 'ededed'}]
            p.update(additions=3684, deletions=67853, head='new5678')
        p['updated'] = iso(NOW - hours * 3600)
        con.execute(
            'insert into pulls values (?,?,?,?,?)',
            (f'example/app#{number}', 'example/app', number, p['updated'], json.dumps(p)),
        )
    con.commit()
    con.close()


def companion(root):
    helper = f'{root}/companions/{OTHER}'
    os.makedirs(helper, exist_ok=True)
    dump(f'{helper}/heartbeat.json', {'name': OTHER, 'agent': 'sara', 'at': time.time() + 10**6, 'connected': True})
    dump(f'{helper}/settings-schema.json', [])
    dump(f'{root}/agents/sara/workspace/.companion/{OTHER}/status.json', {'state': 'not configured', 'error': ''})
    log = f'{root}/agents/admin/workspace/.companion/{COMPANION}/logs/companion.log'
    write(log, '2026-11-02 10:00:00 scout: connected to Slack\n2026-11-02 10:00:05 scout: 1 task waiting\n')
    folder = f'{root}/companions/{COMPANION}'
    os.makedirs(folder, exist_ok=True)
    companion_db(f'{folder}/companion.db')
    dump(
        f'{folder}/template.json',
        {
            'template_from': 'a1b2c3d',
            'template_to': 'e4f5a6b',
            'result': 'conflict',
            'detail': 'template update needs merging (conflicts in: bot/prompts.py)',
            'at': '2026-11-02T04:31:00+03:00',
        },
    )
    dump(
        f'{folder}/heartbeat.json',
        {
            'name': COMPANION,
            'agent': 'admin',
            'at': time.time() + 10**6,  # stays "live" while the throwaway instance runs
            'since': NOW - 86400,
            'connected': True,
            'mode': 'review',
            'workspace': 'example',
            'channels': [
                {'id': 'C1', 'name': 'general', 'member': True},
                {'id': 'C2', 'name': 'random', 'member': False},
            ],
            'people': [{'id': 'U0ALI', 'name': 'Ali', 'avatar': ''}],
            'github': {'ready': True, 'bot': 'scout-example', 'accounts': ['example'], 'at': NOW, 'error': ''},
        },
    )
    dump(
        f'{folder}/settings-schema.json',
        [
            {
                'key': 'mode',
                'label': 'Mode',
                'type': 'choice',
                'options': [
                    {'value': 'review', 'label': 'Review before sending'},
                    {'value': 'auto', 'label': 'Send on its own'},
                ],
                'default': 'review',
            },
            {'key': 'github_user', 'label': 'Your GitHub username', 'type': 'text', 'default': 'example-admin'},
            {'key': 'access', 'label': 'People', 'type': 'people', 'when': {'mode': ['review']}, 'default': []},
        ],
    )
    dump(f'{folder}/settings.json', {})


T3_SCHEMA = """
create table projection_projects (project_id text primary key, title text, deleted_at text);
create table orchestration_v2_projection_threads (thread_id text primary key, project_id text, title text,
  updated_at text, deleted_at text, payload_json text);
create table orchestration_v2_projection_runs (run_id text primary key, thread_id text, status text,
  requested_at text, completed_at text);
create table orchestration_v2_projection_runtime_requests (runtime_request_id text primary key, thread_id text,
  kind text, status text, created_at text, payload_json text);
"""
# agent -> [(thread, title, project, source, parent, [(status, started s ago, done s ago or None)], pending request)]
CHATS = {
    'admin': [
        ('t1', 'Migrate billing to the new API', 'platform', 'user', '', [('running', 1260, None)], ''),
        ('t1a', 'Trace the webhook retries', 'platform', 'mcp', 't1', [('running', 600, None)], ''),
        ('t1b', 'Write the migration tests', 'platform', 'mcp', 't1', [('running', 420, None)], ''),
        ('t2', 'Review platform#6111: refactor(general)', 'platform', 'mcp', '', [('running', 300, None)], ''),
        ('t3', 'Which region should staging use?', 'infra', 'user', '', [('completed', 900, 840)], 'user_input'),
        ('t4', 'Fix the flaky login test', 'web', 'user', '', [('completed', 4000, 3100)], ''),
        ('t5', 'Bump dependencies', 'web', 'user', '', [('failed', 8000, 7600)], ''),
    ],
    'sara': [
        ('s1', 'Draft the quarterly report', 'reports', 'user', '', [('running', 3000, None)], ''),
        ('s2', 'Summarise the incident thread', 'ops', 'mcp', '', [('completed', 2500, 1900)], ''),
    ],
}


def _iso(seconds_ago):
    stamp = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(NOW - seconds_ago))
    return f'{stamp}.000Z'


def t3(root):
    for a in AGENTS:
        folder = f'{root}/agents/{a}/home/.t3/userdata'
        os.makedirs(folder, exist_ok=True)
        if a not in CHATS:
            continue
        con = sqlite3.connect(f'{folder}/statev2.sqlite')
        con.executescript(T3_SCHEMA)
        for tid, title, proj, source, parent, runs, request in CHATS[a]:
            lineage = {'relationshipToParent': 'subagent', 'parentThreadId': parent} if parent else {}
            payload = {'creationSource': source, 'createdBy': source, 'lineage': lineage}
            con.execute('insert or ignore into projection_projects values (?, ?, null)', (proj, proj))
            con.execute(
                'insert into orchestration_v2_projection_threads values (?, ?, ?, ?, null, ?)',
                (tid, proj, title, _iso(0), json.dumps(payload)),
            )
            for n, (status, start, done) in enumerate(runs):
                con.execute(
                    'insert into orchestration_v2_projection_runs values (?, ?, ?, ?, ?)',
                    (f'{tid}-{n}', tid, status, _iso(start), _iso(done) if done is not None else None),
                )
            if request:
                con.execute(
                    "insert into orchestration_v2_projection_runtime_requests values (?, ?, ?, 'pending', ?, '{}')",
                    (f'{tid}-q', tid, request, _iso(780)),
                )
        con.commit()
        con.close()


def main(root):
    shutil.rmtree(root, ignore_errors=True)
    for step in (rendered, watch, secrets, companion, t3):
        step(root)
    os.makedirs(f'{root}/data', exist_ok=True)


if __name__ == '__main__':
    main(sys.argv[1])
