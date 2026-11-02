"""What companion bots publish (contract: companion/companion.py), read-only except settings.json and asks/."""

import json
import os
import sqlite3
import time
import uuid

import cluster

from . import secrets as store_secrets
from .files import read_json, write_json

ROOT = os.environ.get('COMPANIONS_DIR', '/companions')  # each companion publishes into ROOT/<name>/
AGENTS = os.environ.get('AGENTS_DIR', '/agents')  # <data>/agents: each agent's home and workspace
LOG_TAIL = 200_000  # bytes of a companion's log the page shows
LIVE_WITHIN = 45  # s: an older heartbeat means the bot is down
TASKS_SHOWN, EVENTS_SHOWN, POLLS_SHOWN = 300, 600, 20


def _folder(name):
    return os.path.join(ROOT, name)


def _state(heartbeat):
    fresh = time.time() - heartbeat.get('at', 0) < LIVE_WITHIN
    if not fresh:
        return 'offline'
    return 'live' if heartbeat.get('connected') else 'disconnected'


def _polls(con):
    """Open polls first, then the latest closed ones; [] for a bot that runs none (no table)."""
    try:
        rows = con.execute(
            'select id, task, open, closes, data from polls order by open desc, closes desc limit ?', (POLLS_SHOWN,)
        )
        return [
            dict(json.loads(r['data']), id=r['id'], task=r['task'], open=bool(r['open']), closes=r['closes'])
            for r in rows
        ]
    except sqlite3.OperationalError:
        return []


def _pulls(con):
    """Open pull requests, newest activity first; [] for a bot without a GitHub App (no table)."""
    try:
        rows = con.execute('select id, repo, number, updated, data from pulls order by updated desc')
        return [
            dict(json.loads(r['data']), id=r['id'], repo=r['repo'], number=r['number'], updated=r['updated'])
            for r in rows
        ]
    except sqlite3.OperationalError:
        return []


def _read_db(name):
    """(tasks newest first, events newest first, polls, pulls), from the bot's database opened read-only."""
    path = os.path.join(_folder(name), 'companion.db')
    if not os.path.isfile(path):
        return [], [], [], []
    try:
        con = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=3)
        con.row_factory = sqlite3.Row
        try:
            tasks = [dict(r) for r in con.execute('select * from tasks order by started desc limit ?', (TASKS_SHOWN,))]
            events = [
                dict(r, ok=bool(r['ok']))
                for r in con.execute(
                    'select at, kind, title, task, "to", detail, ok from events order by at desc, id desc limit ?',
                    (EVENTS_SHOWN,),
                )
            ]
            polls = _polls(con)
            pulls = _pulls(con)
        finally:
            con.close()
    except sqlite3.Error:
        return [], [], [], []
    for t in tasks:
        t.pop('updated', None)
    return tasks, events, polls, pulls


def status(name):
    """What the companion's runner last wrote in its agent's workspace (state, last error), or {}."""
    agent = cluster.companions().get(name, '')
    return read_json(os.path.join(AGENTS, agent, 'workspace', '.companion', name, 'status.json'), {})


def companion(name):
    heartbeat = read_json(os.path.join(_folder(name), 'heartbeat.json'), {})
    tasks, events, polls, pulls = _read_db(name)
    st = status(name)
    # Not set up yet (its Slack app or secrets are missing): not "down", just waiting for its owner or their agent.
    state = 'unconfigured' if st.get('state') == 'not configured' else _state(heartbeat)
    return {
        'name': name,
        'profile': cluster.companions().get(name, heartbeat.get('agent', '')),
        'display': cluster.display_name(name),
        'url': url(name),
        'problem': st.get('error') or '',
        'heartbeat': heartbeat,
        'state': state,
        'tasks': tasks,
        'events': events,
        'polls': polls,
        'pulls': pulls,
    }


def all_companions():
    return [companion(n) for n in cluster.companions()]


def url(name):
    return f'/agents/{cluster.companions().get(name, "")}/{name}'


def settings(name):
    """[(field, current value)] from the bot's settings-schema.json and the page's settings.json."""
    schema = read_json(os.path.join(_folder(name), 'settings-schema.json'), [])
    current = read_json(os.path.join(_folder(name), 'settings.json'), {})
    return [(f, current.get(f['key'], f.get('default'))) for f in schema]


def _checked(field, value):
    if field['type'] == 'choice' and value not in [o['value'] for o in field.get('options', [])]:
        raise ValueError('Not one of the options.')
    if field['type'] == 'bool':
        return bool(value)
    if field['type'] == 'text':
        return str(value)[:500]
    return value


def set_setting(name, key, value):
    """Validate against the schema, then write settings.json (the bot re-reads it within seconds). Returns the field."""
    if name not in cluster.companions():
        raise ValueError('Unknown companion.')
    field = {f['key']: f for f, _ in settings(name)}.get(key)
    if not field:
        raise ValueError('Unknown setting.')
    path = os.path.join(_folder(name), 'settings.json')
    current = read_json(path, {})
    current[key] = _checked(field, value)
    write_json(path, current)
    return field


def channels(name):
    """[{id, name, member}] the bot offers for asks, or None when it takes no asks."""
    return read_json(os.path.join(_folder(name), 'heartbeat.json'), {}).get('channels')


def ask(name, text, channel, review):
    """Drop an ask for the bot (it takes it within seconds). The channel must be one it can post in, or ''."""
    text = str(text or '').strip()
    if not text:
        raise ValueError('Write what you want first.')
    if len(text) > 4000:
        raise ValueError('That is too long (4000 characters at most).')
    known = {c['id']: c for c in channels(name) or []}
    if channel and channel not in known:
        raise ValueError('Unknown channel.')
    if channel and not known[channel].get('member'):
        raise ValueError(
            f'{cluster.display_name(name)} is not in #{known[channel]["name"]} yet: invite it there first.'
        )
    path = os.path.join(_folder(name), 'asks', f'{time.time_ns()}-{uuid.uuid4().hex[:6]}.json')
    write_json(path, {'text': text, 'channel': channel or '', 'review': bool(review), 'at': time.time()})


def log_tail(name):
    """(the end of the companion's log, written at) from its agent's workspace; ('', 0) before it ever ran."""
    agent = cluster.companions().get(name, '')
    path = os.path.join(AGENTS, agent, 'workspace', '.companion', name, 'logs', 'companion.log')
    try:
        with open(path, 'rb') as f:
            f.seek(max(0, os.path.getsize(path) - LOG_TAIL))
            return f.read().decode('utf-8', 'replace'), os.path.getmtime(path)
    except OSError:
        return '', 0


def save_secret(name, file, value):
    """Set one of the companion's own secrets (created when missing); the watcher restarts it. False if unchanged."""
    path = f'companions/{name}/{file}'
    if path not in store_secrets.secrets_map():
        raise ValueError('Not one of its secrets.')
    exists = path in {s['name'] for s in store_secrets.all_secrets()}
    return store_secrets.save(path, value, create=not exists)


def _drop(name, ask):
    write_json(os.path.join(_folder(name), 'asks', f'{time.time_ns()}-{uuid.uuid4().hex[:6]}.json'), ask)


def pulls_refresh(name):
    """Ask the bot to re-read the open pull requests from GitHub now (the page does on open and on refresh)."""
    _drop(name, {'type': 'pulls', 'at': time.time()})


def review(name, pr_id):
    """Ask the bot to review one of the pull requests it listed ("owner/repo#123")."""
    pr = next((p for p in companion(name)['pulls'] if p['id'] == pr_id), None)
    if not pr:
        raise ValueError('That pull request is not in the list any more; refresh it.')
    _drop(name, {'type': 'review', 'repo': pr['repo'], 'number': pr['number'], 'at': time.time()})
    return pr


def poll_change(name, poll, b):
    """Ask the bot to change one of its open polls: single / multiple choice, closing time (epoch), or close now."""
    if poll not in {p['id'] for p in companion(name)['polls'] if p['open']}:
        raise ValueError('That poll is not open.')
    change = {'type': 'poll', 'poll': poll}
    if 'multiple' in b:
        change['multiple'] = bool(b['multiple'])
    if b.get('closes'):
        closes = float(b['closes'])
        if closes <= time.time():
            raise ValueError('Pick a closing time in the future.')
        change['closes'] = closes
    if b.get('close'):
        change['close'] = True
    if len(change) == 2:
        raise ValueError('Nothing to change.')
    _drop(name, change)
