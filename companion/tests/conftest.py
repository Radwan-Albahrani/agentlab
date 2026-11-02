"""The companion under test: fake secrets and a throwaway data folder (set before the companion is imported, since its config is read
at import), Slack replaced by a recording client, background jobs run inline. Nothing reaches Slack or T3."""

import json
import os
import tempfile
import time

import pytest

ROOT = tempfile.mkdtemp(prefix='companion-test-')
OWNER = 'U_OWNER'
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
    config,
    drafts,
    errands,
    jobs,
    outbox,
    polls,
    posts,
    publish,
    requests,
    routing,
    slack,
    state,
    t3,
)

COMPANION_DIR = os.path.join(ROOT, 'data')
NAMES = {OWNER: 'Sam', 'U_SALAH': 'Salah', 'U_ALI': 'Ali Example'}


class FakeSlack:
    """The bot client: remembers every message, update and upload, answers the lookups the companion makes."""

    token = 'xoxb-test'

    def __init__(self):
        self.messages, self.updates, self.uploads = [], [], []

    def chat_postMessage(self, **kw):  # noqa: N802 (Slack SDK method names)
        self.messages.append(kw)
        return {'ts': f'{len(self.messages)}.0'}

    def chat_update(self, **kw):
        self.updates.append(kw)
        return {}

    def files_upload_v2(self, **kw):
        self.uploads.append(kw)
        return {}

    def conversations_open(self, users):
        return {'channel': {'id': 'D_OWNER' if users == OWNER else 'D_' + users}}

    def conversations_history(self, **kw):
        return {'messages': [{'text': 'head', 'blocks': [{'type': 'actions'}]}]}

    def conversations_replies(self, **kw):
        return {'messages': []}

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
        """The button ids of every message, in order."""
        return [
            [e['action_id'] for b in m.get('blocks') or [] if b.get('type') == 'actions' for e in b['elements']]
            for m in self.messages
        ]

    def text(self):
        return json.dumps(self.messages + self.updates)


class FakeUserClient(FakeSlack):
    """The owner's read-only token: what they can see in conversations the companion isn't in."""

    root_user = 'U_SALAH'

    def conversations_replies(self, **kw):
        return {'messages': [{'user': self.root_user, 'ts': kw.get('ts', '1.0'), 'text': 'please send the invoices'}]}

    def conversations_history(self, **kw):
        return {'messages': []}


@pytest.fixture(autouse=True)
def fresh_bot(monkeypatch):
    """Every test starts with no tasks, default settings, a fresh fake Slack and inline background jobs."""
    bot, user = FakeSlack(), FakeUserClient()
    monkeypatch.setattr(slack.app, '_client', bot)
    monkeypatch.setattr(slack, 'USER', user)
    monkeypatch.setattr(slack, '_others', {})
    monkeypatch.setattr(slack, '_bot', [])
    monkeypatch.setattr(slack, '_people', {'at': 0.0, 'list': [], 'by_id': {}})
    monkeypatch.setattr(jobs, 'run_later', lambda fn, *args: fn(*args))
    monkeypatch.setattr(config, 'log', lambda *a: None)
    monkeypatch.setattr(slack, '_channels', {'at': 0.0, 'list': []})
    for module in (errands, outbox, requests, routing, publish, drafts, asks, posts, polls):
        if hasattr(module, 'log'):
            monkeypatch.setattr(module, 'log', lambda *a: None)
    state.state['tasks'].clear()
    state.state['refused'].clear()
    state.state['drafts'].clear()
    state.state['polls'].clear()
    state.state.pop('awaiting_invite', None)
    requests._pending.clear()
    requests._known.clear()
    routing._seen.clear()
    publish._last = 0.0
    set_settings({})
    yield bot


def set_settings(values):
    """What the hub writes; the bumped mtime makes the companion re-read it at once."""
    path = os.path.join(COMPANION_DIR, 'settings.json')
    with open(path, 'w') as f:
        json.dump(values, f)
    stamp = time.time() + 1000 + len(json.dumps(values))
    os.utime(path, (stamp, stamp))


@pytest.fixture
def t3_quiet(monkeypatch):
    """T3 that answers nothing interesting; tests override what they need."""
    monkeypatch.setattr(t3, 'busy', lambda tid: False)
    monkeypatch.setattr(t3, 'waiting_question', lambda tid: False)
    monkeypatch.setattr(t3, 'has_open_run', lambda tid: False)
    monkeypatch.setattr(t3, 'run_error', lambda tid: '')
    monkeypatch.setattr(t3, 'send', lambda tid, msg: {'ok': True})
    monkeypatch.setattr(t3, 'start_thread', lambda project, title, message: ('T_NEW', ''))
    return t3
