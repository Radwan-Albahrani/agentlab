"""The companion's persisted state (tasks keyed by Slack thread, polls, drafts...); access it under `lock`."""

import json
import threading
import time
from datetime import UTC, datetime

from .config import COMP, default_project

lock = threading.RLock()
_written = {}  # store key -> JSON last written


def _rows(s):
    """Store rows: task:<key> per task, other top-level keys as themselves."""
    rows = {f'task:{k}': t for k, t in s['tasks'].items()}
    rows.update((k, v) for k, v in s.items() if k != 'tasks')
    return rows


def _load():
    rows = COMP.store_all()
    s = {'tasks': {k[5:]: v for k, v in rows.items() if k.startswith('task:')}}
    s.update((k, v) for k, v in rows.items() if not k.startswith('task:'))
    s.setdefault('refused', [])
    s.setdefault('drafts', {})
    s.setdefault('polls', {})
    _written.update((k, json.dumps(v, sort_keys=True)) for k, v in _rows(s).items())
    return s


state = _load()


def save():
    with lock:
        rows = _rows(state)
        dumped = {k: json.dumps(v, sort_keys=True) for k, v in rows.items()}
        changed = {k: rows[k] for k, d in dumped.items() if _written.get(k) != d}
        gone = [k for k in _written if k not in rows]
        COMP.store_put(changed)
        if gone:
            COMP.store_delete(gone)
        for k in gone:
            del _written[k]
        _written.update((k, dumped[k]) for k in changed)


def key(channel, thread_ts):
    return f'{channel}:{thread_ts}'


def tasks():
    return state['tasks']


def task_of(channel, thread_ts):
    return state['tasks'].get(key(channel, thread_ts))


def now_iso():
    """Now in T3's timestamp format; compared as strings with T3's, so keep the format exact."""
    return datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'


def parse_iso(iso):
    return datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp() if iso else 0.0


def new_task(channel, thread_ts, thread, title, outbox, trigger_ts, status_ts, project=None, **extra):
    now = now_iso()
    t = {
        'thread': thread,
        'title': title,
        'project': project or default_project(),
        'channel': channel,
        'thread_ts': thread_ts,
        'outbox': outbox,
        'trigger_ts': trigger_ts,
        'status_ts': status_ts,
        'active': True,
        'start': now,
        'burst_start': now,
        'seen': now,
        'step_from': now,
        'asked': [],
        'prs': [],
        'workers_said': 0,
        'last_status': '',
        'last_status_at': 0,
        'quiet_since': 0,
        'options': {},
        'line_start': time.time(),
        **extra,
    }
    with lock:
        state['tasks'][key(channel, thread_ts)] = t
    save()
    return t


def prepare_for_start():
    """Normalise loaded tasks after a restart."""
    for t in state['tasks'].values():
        if not t.get('active'):
            t['status_ts'] = None
        t.setdefault('project', default_project())
        # older versions left the draft an approved reply replaced, so the task kept waiting for Send
        if (t.get('closed') or '').startswith(':white_check_mark: Done · sent to ') and not t.get('reply_pending'):
            t.pop('reply_draft', None)
