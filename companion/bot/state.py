"""The companion's memory: one task per Slack thread it keeps in sync with a T3 chat, plus drafts, refusals and tags
waiting for an invite. Kept in the companion database's store (one row per task, one per other key); save() writes
only what changed. The poller and Slack handlers share it under `lock`.

A task (state['tasks'][key(channel, thread_ts)]):
  thread, title, project, channel, thread_ts, outbox     the T3 chat and the Slack thread mirroring it
  active, start, ended, outcome, closed                  lifecycle
  burst_start, seen, step_from, latest, status_ts, ...   the live "thinking" line of the current turn
  requester, source*, approval, reply_draft, cred_ask    errands: done for someone else, through the owner's DM
  review, post_draft, poll                               asks from the hub: a post for a channel
  review                                                 a pull request review: the PR, its head, what was posted
state['polls'][id]: a poll the companion runs in a channel (see polls).
state['pulls'], state['review_queue']: the open PRs its GitHub App sees, and reviews waiting for a slot."""

import json
import threading
import time
from datetime import UTC, datetime

from .config import COMP, default_project

lock = threading.RLock()
_written = {}  # store key -> JSON last written


def _rows(s):
    """The state as store rows: task:<key> per task, the other top-level keys as themselves."""
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
    """T3's timestamp format, so they compare as strings with the database's."""
    return datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'


def parse_iso(iso):
    return datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp() if iso else 0.0


def new_task(channel, thread_ts, thread, title, outbox, trigger_ts, status_ts, project=None, **extra):
    """Register a task that starts now and is followed by the poller."""
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
    """After a restart: answered turns never reuse their old "thinking" message."""
    for t in state['tasks'].values():
        if not t.get('active'):
            t['status_ts'] = None
        t.setdefault('project', default_project())
