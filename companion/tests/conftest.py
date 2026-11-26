"""Fake secrets and data folder (set before importing bot: config reads at import), recording Slack, inline jobs."""

import json
import os
import tempfile
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = tempfile.mkdtemp(prefix='companion-test-')
OWNER = 'U_OWNER'
ROUTE = {'project': '/workspace/platform', 'by': 'default', 'why': 'nothing named a project'}  # bot/projects.py
for sub in ('secrets', 'data', 'files', 't3'):
    os.makedirs(os.path.join(ROOT, sub))
for name, value in {
    'owner.txt': OWNER,
    'bot-token.txt': 'xoxb-test',
    'app-token.txt': 'xapp-test',
    'user-token.txt': 'xoxp-test',
    'agent-key.txt': 'key',
}.items():
    with open(os.path.join(ROOT, 'secrets', name), 'w') as f:
        f.write(value)
os.environ.update(
    COMPANION_SECRETS=f'{ROOT}/secrets',
    COMPANION_DATA=f'{ROOT}/data',
    COMPANION_FILES=f'{ROOT}/files',
    COMPANION_T3=f'{ROOT}/t3',
    COMPANION_MODE='tag',
    COMPANION_PUBLISH_CHANNEL='C_UPDATES',
)

from bot import (  # noqa: E402
    asks,
    cases,
    config,
    drafts,
    errands,
    jobs,
    ledger,
    machine,
    outbox,
    polls,
    posts,
    publish,
    requests,
    routing,
    slack,
    state,
    t3,
    t3db,
)

COMPANION_DIR = os.path.join(ROOT, 'data')
NAMES = {OWNER: 'Sam', 'U_SALAH': 'Salah', 'U_ALI': 'Ali Example'}


class FakeSlack:
    """Fake bot client recording messages, updates and uploads."""

    token = 'xoxb-test'

    def __init__(self):
        self.messages, self.updates, self.uploads = [], [], []
        self.sent = []  # messages and uploads, in the order they went
        self.threads = {}  # (channel, root ts) -> its messages, as conversations_replies gives them

    def chat_postMessage(self, **kw):  # noqa: N802 (Slack SDK method names)
        self.messages.append(kw)
        self.sent.append(kw)
        ts = f'{len(self.messages)}.0'
        root = kw.get('thread_ts') or ts
        posted = {'ts': ts, 'thread_ts': root, 'user': 'BCOMPANION', 'bot_id': 'B_COMPANION'}
        self.threads.setdefault((kw['channel'], root), []).append(
            posted | {'text': kw.get('text') or '', 'blocks': kw.get('blocks') or []}
        )
        return {'ts': ts}

    def chat_update(self, **kw):
        self.updates.append(kw)
        for (ch, _), msgs in self.threads.items():
            for m in msgs:
                if ch == kw['channel'] and m['ts'] == kw['ts']:
                    m.update(text=kw.get('text') or '', blocks=kw.get('blocks') or [])
        return {}

    def files_upload_v2(self, **kw):
        self.uploads.append(kw)
        self.sent.append(kw)
        return {'files': [{'id': f'F{len(self.uploads)}'}]}

    def files_info(self, file):
        n = int(file[1:])
        return {'file': {'shares': {'private': {self.uploads[n - 1]['channel']: [{'ts': f'{n}.5'}]}}}}

    def say(self, channel, root, ts, user, text, files=None):
        """Someone writes in a thread: it is there for conversations_replies; -> the Slack event."""
        msg = {'ts': ts, 'thread_ts': root, 'user': user, 'text': text} | ({'files': files} if files else {})
        self.threads.setdefault((channel, root), []).append(msg)
        return dict(msg, channel=channel, channel_type='im' if channel.startswith('D') else 'channel')

    def conversations_open(self, users):
        return {'channel': {'id': 'D_OWNER' if users == OWNER else 'D_' + users}}

    def conversations_history(self, **kw):
        if kw.get('channel') == 'D_SALAH':  # the owner's DM with Salah: not the bot's to read
            raise Exception("The server responded with: {'ok': False, 'error': 'channel_not_found'}")
        return {'messages': [{'text': 'head', 'blocks': [{'type': 'actions'}]}]}

    def conversations_replies(self, **kw):
        return {'messages': list(self.threads.get((kw['channel'], kw['ts']), []))}

    def conversations_info(self, channel):
        return {'channel': {'name': 'general', 'is_member': True}}

    def chat_getPermalink(self, **kw):  # noqa: N802
        return {'permalink': 'https://x.slack.com/archives/C1/p1'}

    def users_info(self, user):
        return {'user': {'real_name': NAMES.get(user, user), 'profile': {'image_48': f'https://img/{user}.png'}}}

    def auth_test(self):
        return {'user_id': 'BCOMPANION', 'url': 'https://x.slack.com/'}

    def users_list(self, **kw):
        return {
            'members': [
                {'id': 'U_ALI', 'name': 'ali', 'real_name': 'Ali Example', 'profile': {'display_name': 'Ali'}},
                {'id': 'U_ALI2', 'name': 'ali.k', 'real_name': 'Ali Khan', 'profile': {}},
                {'id': 'U_GONE', 'name': 'gone', 'real_name': 'Gone Person', 'deleted': True},
            ]
        }

    def conversations_list(self, **kw):
        return {
            'channels': [
                {'id': 'C_RANDOM', 'name': 'random', 'is_member': True},
                {'id': 'C_TECH', 'name': 'ask-tech', 'is_member': True},
                {'id': 'C_ELSEWHERE', 'name': 'elsewhere', 'is_member': False},
            ]
        }

    def reactions_add(self, **kw):
        return {}

    reactions_remove = reactions_add

    def actions(self):
        return [
            [e['action_id'] for b in m.get('blocks') or [] if b.get('type') == 'actions' for e in b['elements']]
            for m in self.messages
        ]

    def text(self):
        return json.dumps(self.messages + self.updates)


class FakeUserClient(FakeSlack):
    """Fake owner user-token client."""

    root_user = 'U_SALAH'

    def conversations_replies(self, **kw):
        return {'messages': [{'user': self.root_user, 'ts': kw.get('ts', '1.0'), 'text': 'please send the invoices'}]}

    def conversations_history(self, **kw):
        return {'messages': []}


@pytest.fixture(autouse=True)
def fresh_bot(monkeypatch):
    bot, user = FakeSlack(), FakeUserClient()
    monkeypatch.setattr(slack.app, '_client', bot)
    monkeypatch.setattr(slack, 'USER', user)
    monkeypatch.setattr(slack, '_others', {})
    monkeypatch.setattr(slack, '_bot', [])
    monkeypatch.setattr(slack, '_people', {'at': 0.0, 'list': [], 'by_id': {}})
    monkeypatch.setattr(jobs, 'run_later', lambda fn, *args: fn(*args))
    monkeypatch.setattr(t3, 'agent_up', lambda: True)
    bot.released = []  # chats whose worktrees the agent was told to remove
    monkeypatch.setattr(t3, 'release', lambda tid: bot.released.append(tid) or {'ok': True})
    monkeypatch.setattr(config, 'log', lambda *a: None)
    monkeypatch.setattr(slack, '_channels', {'at': 0.0, 'list': []})
    for module in (errands, outbox, requests, routing, publish, drafts, asks, posts, polls, cases, ledger, machine):
        if hasattr(module, 'log'):
            monkeypatch.setattr(module, 'log', lambda *a: None)
    state.state['tasks'].clear()
    state.state['refused'].clear()
    state.state['drafts'].clear()
    state.state['polls'].clear()
    state.state.pop('awaiting_invite', None)
    state.state.pop('inbox', None)
    requests._pending.clear()
    requests._known.clear()
    routing._seen.clear()
    publish._last = 0.0
    set_settings({})
    yield bot


def agent_sends(task, *items, raw=None):
    """The agent writes send.json (these items, or `raw` as the whole file) and the outbox takes it."""
    box = os.path.join(outbox.OUTBOX, task['outbox'])
    os.makedirs(box, exist_ok=True)
    with open(os.path.join(box, 'send.json'), 'w') as f:
        json.dump(raw if raw is not None else list(items), f)
    outbox.tick(task)
    return box


def receipts(box):
    """What the agent reads back: outbox/<task>/receipts.json."""
    with open(os.path.join(box, 'receipts.json')) as f:
        return json.load(f)


HANDLERS = {  # the buttons, wired as slack.app.action wires them (errands.py, posts.py)
    'errand_approve': errands.owner_action(lambda t, k, ts: errands.decide(t, k, True, ts), card=True),
    'errand_reject': errands.owner_action(lambda t, k, ts: errands.decide(t, k, False, ts), card=True),
    'post_send': errands.owner_action(lambda t, k, ts: posts.decide(t, k, True, ts), card=True),
    'post_skip': errands.owner_action(lambda t, k, ts: posts.decide(t, k, False, ts), card=True),
    'reply_send': errands.owner_action(lambda t, k, ts: errands.decide_reply(t, k, True, ts), card=True),
    'reply_skip': errands.owner_action(lambda t, k, ts: errands.decide_reply(t, k, False, ts), card=True),
    'cred_send': errands.owner_action(lambda t, k, ts: errands.decide_credential(t, k, True, ts), card=True),
    'cred_skip': errands.owner_action(lambda t, k, ts: errands.decide_credential(t, k, False, ts), card=True),
}


def click(bot, action_id, user=OWNER, nth=-1):
    """Press `action_id` on the nth message carrying it (default: the latest), as Slack would; -> that card's ts."""
    found = [
        (i, e)
        for i, m in enumerate(bot.messages)
        for b in m.get('blocks') or []
        if b.get('type') == 'actions'
        for e in b['elements']
        if e['action_id'] == action_id
    ]
    i, e = found[nth]
    ts = f'{i + 1}.0'  # FakeSlack's ts for message i
    body = {
        'user': {'id': user},
        'actions': [{'value': e.get('value') or ''}],
        'channel': {'id': bot.messages[i]['channel']},
        'message': {'ts': ts},
    }
    HANDLERS[action_id](lambda: None, body)
    return ts


def ended(task, outcome='answered'):
    """End the turn under way, as a finished chat would."""
    machine.end_turn(task, outcome)


def set_settings(values):
    """Write settings.json with a bumped mtime so it is re-read at once."""
    path = os.path.join(COMPANION_DIR, 'settings.json')
    with open(path, 'w') as f:
        json.dump(values, f)
    stamp = time.time() + 1000 + len(json.dumps(values))
    os.utime(path, (stamp, stamp))


@pytest.fixture
def t3_quiet(monkeypatch):
    """Idle fake T3; tests override what they need."""
    monkeypatch.setattr(t3, 'busy', lambda tid: False)
    monkeypatch.setattr(t3, 'waiting_question', lambda tid: False)
    monkeypatch.setattr(t3, 'has_open_run', lambda tid: False)
    monkeypatch.setattr(t3, 'run_error', lambda tid: '')
    monkeypatch.setattr(t3, 'send', lambda tid, msg: {'ok': True})
    monkeypatch.setattr(t3, 'start_thread', lambda project, title, message: ('T_NEW', ''))
    return t3


@pytest.fixture
def t3_rows(tmp_path, monkeypatch):
    """T3's database as the companion reads it (bot/t3db.py), empty: a session to add rows with."""
    engine = create_engine(f'sqlite:///{tmp_path}/statev2.sqlite')
    t3db.Base.metadata.create_all(engine)
    monkeypatch.setattr(t3db, 'engine', lambda: engine)
    with Session(engine) as s:
        yield s
