"""Example on-disk data for the hub's tests and throwaway instance: python3 fixtures.py <folder> (wipes it first)."""

import json
import os
import shutil
import sys
import time
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the hub's modules
from notify.t3schema import Base as T3Base
from notify.t3schema import Project, Request, Run, Thread
from store.companion_tables import Base, Event, Item, Poll, Pull, TaskCard

AGENTS = ('admin', 'sara', 'lab')
OWNER = {'admin': 'admin@example.com', 'sara': 'sara@example.com', 'lab': 'sara@example.com'}
COMPANION = 'scout'  # admin's; OTHER is sara's
OTHER = 'helper'
GB = 2**30
NOW = time.time()


def cluster(root: str) -> dict[str, Any]:
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


def dump(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=1)


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)


def container(
    name: str, service: str, stack: str, state: str = 'running', status: str = 'Up 2 hours (healthy)'
) -> dict[str, str]:
    return {'name': name, 'service': service, 'stack': stack, 'state': state, 'status': status, 'image': 'example'}


def watch(root: str) -> None:
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


def rendered(root: str) -> None:
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


def secrets(root: str) -> None:
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


LedgerRow = tuple[str, str, int, dict[str, Any]]  # (kind, state, seconds ago, data)


def ledger_items() -> list[Item]:
    """The companion's ledger (companion/bot/ledger.py): every message in and out of a task, with its state."""

    def walk(*states: str, start: float) -> list[list[str | float]]:
        return [[s, start + 5 * i, ''] for i, s in enumerate(states)]

    t2: list[LedgerRow] = [  # Sara's case: what she wrote, what went to her, the owner's private word, and what waits on them
        ('in', 'received', 290, {'label': 'Sara', 'text': 'Can you summarise the incident thread for the postmortem?'}),
        ('message', 'sent', 240, {'to': 'colleague', 'label': 'Sara',
                                  'text': 'Here is the summary:\n- 09:12 alerts fired\n- 09:40 fixed'}),
        ('final', 'sent', 235, {'to': 'case', 'label': 'you',
                                'text': 'Sent Sara the summary. I did not read the on-call notes yet.'}),
        ('in', 'received', 200, {'label': 'Admin', 'private': True, 'text': 'Did you check the on-call notes too?'}),
        ('final', 'sent', 180, {'to': 'case', 'label': 'you', 'text': 'Not yet: they add one more step at 09:31.'}),
        ('message', 'sent', 150, {'to': 'colleague', 'label': 'Sara', 'text': 'One more step at 09:31, from on-call.'}),
        ('message', 'refused', 130, {'to': '', 'text': 'Posted it.', 'note': '"to" is required: the person, "owner", '
                                     '"thread", or "#channel"'}),
        ('approval', 'replaced', 120, {'action': 'Post the summary in #general', 'note': 'replaced by a newer request: Post the summary in #incidents'}),
        ('approval', 'awaiting_owner', 100, {'action': 'Post the summary in #incidents',
                                            'details': 'A new message in #incidents, from Leafy, for the postmortem.'}),
    ]  # fmt: skip
    t1: list[LedgerRow] = [
        ('in', 'received', 900, {'label': 'Sara', 'text': 'Draft the release notes for 2.4'}),
        ('approval', 'awaiting_owner', 600, {'action': 'Publish the release notes draft to the docs site'}),
    ]
    t3: list[LedgerRow] = [  # an errand: the requester's ask, the reply the owner sent on with Send
        ('in', 'received', 7200, {'label': 'Omar', 'text': 'Can you book a room for the 10:00 sync?'}),
        ('message', 'sent', 7000, {'to': 'requester', 'label': 'Omar', 'text': 'Booked: Room 2 at 10:00.'}),
        ('final', 'sent', 6990, {'to': 'thread', 'text': 'Booked Room 2 and told Omar.'}),
    ]
    paths = {
        'received': ('received',),
        'sent': ('received', 'sent'),
        'refused': ('received', 'refused'),
        'replaced': ('received', 'awaiting_owner', 'replaced'),
        'awaiting_owner': ('received', 'awaiting_owner'),
    }
    rows = []
    for task, items in (('t1', t1), ('t2', t2), ('t3', t3)):
        for seq, (kind, state, ago, data) in enumerate(items, 1):
            at = NOW - ago
            history = walk(*(('sent',) if kind == 'final' else paths[state]), start=at)
            payload: dict[str, Any] = {**data, 'history': history}
            rows.append(
                Item(id=f'{task}#{seq}', task=task, seq=seq, kind=kind, state=state, at=at, data=payload, updated=NOW)
            )
    return rows


def iso(t: float) -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(t))


def task_cards(slack: str) -> list[TaskCard]:
    case_link = 'https://example.slack.com/archives/D0OWNER/p2'
    # where each chat started and why (companion/bot/projects.py); t3 is from a companion too old to say
    route = {'project': '/workspace/app/apps/api', 'route_by': 'named', 'route_why': 'the ask names "api"'}
    common = {'requester': 'Sara', 'slack': slack, 'source': 'slack', 'updated': NOW}
    return [
        TaskCard(
            **common,
            **route,
            id='t1',
            title='Draft the release notes',
            kind='task',
            status='waiting',
            waiting='approval',
            started=iso(NOW - 900),
            thread='th1',
            party='colleague',
            phase='waiting_owner',
            case_link=case_link,
        ),
        TaskCard(
            **common,
            **route,
            id='t2',
            title='Summarise the incident thread',
            kind='task',
            status='working',
            started=iso(NOW - 300),
            thread='th2',
            started_by='Sara',
            via='in the requests channel #asks',
            approved_by='Admin',
            party='colleague',
            phase='waiting_owner',
            case_link=case_link,
        ),
        TaskCard(
            **(common | {'requester': 'Admin'}),
            id='t3',
            title='Book the meeting room',
            kind='errand',
            status='done',
            outcome='Booked.',
            started=iso(NOW - 7200),
            ended=iso(NOW - 7000),
            party='errand',
            phase='answered',
            case_link=case_link,
        ),
        TaskCard(
            **(common | {'requester': '', 'slack': ''}),
            **route,
            id='t4',
            title='Review example/app#12',
            kind='review',
            status='done',
            outcome='Review posted on <https://github.com/example/app/pull/12#issuecomment-1|example/app#12> · 2 findings',
            started=iso(NOW - 5000),
            ended=iso(NOW - 4000),
            thread='th4',
            via='from the hub',
            party='owner',
            phase='answered',
        ),
    ]


def companion_db(path: str) -> None:
    slack = 'https://example.slack.com/archives/C0EXAMPLE/p1'
    events = [
        (NOW - 7000, 'sent', 'Booked the meeting room', 't3', '#general', 'Room 2, 10:00', 1),
        (NOW - 3000, 'files', 'Shared the report', 't2', 'Sara', 'report.pdf', 1),
        (NOW - 2500, 'sent', 'Review of example/app#12: 2 findings · QA verified', 't4', 'example/app#12', '', 1),
        (NOW - 2400, 'sent', 'Review result for app#12', None, 'Omar', 'Slack refused the DM: not_in_channel', 0),
        (NOW - 120, 'task', 'New task from Sara', 't2', '', '', 1),
        # t2 is a case: Sara's conversation, the owner's private exchange about it, a message sent on their word
        (
            NOW - 290,
            'received',
            'Sara wrote',
            't2',
            None,
            'Can you summarise the incident thread for the postmortem?',
            1,
        ),
        (
            NOW - 240,
            'sent',
            'Reply to Sara',
            't2',
            'Sara',
            'Here is the summary:\n- 09:12 alerts fired\n- 09:40 fixed',
            1,
        ),
        (NOW - 200, 'private', 'You asked Leafy', 't2', None, 'Did you check the on-call notes too?', 1),
        (NOW - 180, 'private', 'Leafy answered you', 't2', None, 'Not yet: they add one more step at 09:31.', 1),
        (NOW - 150, 'sent', 'Message to Sara (on your word)', 't2', 'Sara', 'One more step at 09:31, from on-call.', 1),
        (NOW - 100, 'approval', 'Asked you to approve: post the summary in #incidents', 't2', None, 'for Sara', 1),
    ]
    rows: list[object] = [*task_cards(slack), *ledger_items()]
    rows += [
        Event(at=at, kind=kind, title=title, task=task, to=to, detail=detail, ok=bool(ok))
        for at, kind, title, task, to, detail, ok in events
    ]
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
    rows.append(Poll(id='p1', task='t1', open=True, closes=NOW + 86400, data=poll, updated=NOW))
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
                'detail': {
                    'findings': [
                        {
                            'title': 'Revoked grants survive the migration',
                            'severity': 'blocking',
                            'lane': 'correctness',
                            'path': 'api/src/migrate/inputs.ts',
                            'line': 88,
                            'start_line': 80,
                            'body': 'The stop list is applied before the role defaults, so a grant revoked for a role '
                            'comes back on the next run.',
                            'link': 'https://github.com/example/app/blob/old1234/api/src/migrate/inputs.ts#L80-L88',
                        },
                        {
                            'title': 'migratedAdditionsFor re-reads the same table per role',
                            'severity': 'non-blocking',
                            'lane': 'performance',
                            'path': 'api/src/migrate/additions.ts',
                            'line': 41,
                            'start_line': None,
                            'body': 'Load the grants once and group them; 40 roles means 40 queries today.',
                            'link': 'https://github.com/example/app/blob/old1234/api/src/migrate/additions.ts#L41',
                        },
                    ],
                    'qa': {
                        'verdict': 'partial',
                        'text': '4 of 6 claims verified. Revoking a grant could not be checked: the staging seed has no '
                        'revoked grants.',
                        'url': 'https://github.com/example/app/pull/15#issuecomment-1',
                    },
                    'review_url': 'https://github.com/example/app/pull/15#pullrequestreview-1',
                },
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
        rows.append(Pull(id=f'example/app#{number}', repo='example/app', number=number, updated=p['updated'], data=p))
    engine = create_engine(f'sqlite:///{path}')
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all(rows)
        s.commit()
    engine.dispose()


def companion(root: str) -> None:
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
            'github': {
                'ready': True,
                'bot': 'scout-example',
                'accounts': ['example'],
                'at': NOW,
                'error': '',
                'repos': ['example/qa-evidence', 'example/secrets'],
            },
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
            {
                'key': 'qa_evidence_repo',
                'label': 'QA screenshots repository',
                'type': 'text',
                'default': '',
                'source': 'github_repos',
            },
        ],
    )
    dump(f'{folder}/settings.json', {})


# agent -> [(thread, title, project, source, parent, [(status, started s ago, done s ago or None)], pending request)]
Chat = tuple[str, str, str, str, str, list[tuple[str, int, int | None]], str]
CHATS: dict[str, list[Chat]] = {
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


def _iso(seconds_ago: float) -> str:
    stamp = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(NOW - seconds_ago))
    return f'{stamp}.000Z'


def t3_rows(chats: list[Chat]) -> list[object]:
    rows: list[object] = [Project(project_id=p, title=p) for p in dict.fromkeys(c[2] for c in chats)]
    for tid, title, proj, source, parent, runs, request in chats:
        lineage = {'relationshipToParent': 'subagent', 'parentThreadId': parent} if parent else {}
        payload = {'creationSource': source, 'createdBy': source, 'lineage': lineage}
        rows.append(Thread(thread_id=tid, project_id=proj, title=title, updated_at=_iso(0), payload=payload))
        rows += [
            Run(
                run_id=f'{tid}-{n}',
                thread_id=tid,
                status=status,
                requested_at=_iso(start),
                completed_at=_iso(done) if done is not None else None,
            )
            for n, (status, start, done) in enumerate(runs)
        ]
        if request:
            rows.append(
                Request(
                    runtime_request_id=f'{tid}-q',
                    thread_id=tid,
                    kind=request,
                    status='pending',
                    created_at=_iso(780),
                    payload={},
                )
            )
    return rows


def t3(root: str) -> None:
    for a in AGENTS:
        folder = f'{root}/agents/{a}/home/.t3/userdata'
        os.makedirs(folder, exist_ok=True)
        if a not in CHATS:
            continue
        engine = create_engine(f'sqlite:///{folder}/statev2.sqlite')
        # the hub's own models first: they map columns t3schema leaves out (a message's run, a request's time)
        Request.metadata.create_all(engine)
        T3Base.metadata.create_all(engine)
        with Session(engine) as s:
            s.add_all(t3_rows(CHATS[a]))
            s.commit()
        engine.dispose()


def main(root: str) -> None:
    shutil.rmtree(root, ignore_errors=True)
    for step in (rendered, watch, secrets, companion, t3):
        step(root)
    os.makedirs(f'{root}/data', exist_ok=True)


if __name__ == '__main__':
    main(sys.argv[1])
