"""The companion's persisted state (tasks keyed by Slack thread, see key_of; polls, drafts...); access it under `lock`."""

import json
import threading
from datetime import UTC, datetime
from typing import Any, Unpack, cast

from .config import COMP, default_project
from .shapes import Line, Review, Route, State, Task

lock = threading.RLock()
_written: dict[str, str] = {}  # store key -> JSON last written


def _rows(s: State) -> dict[str, Any]:
    """Store rows: task:<key> per task, other top-level keys as themselves."""
    rows: dict[str, Any] = {f'task:{k}': t for k, t in s['tasks'].items()}
    rows.update((k, v) for k, v in s.items() if k != 'tasks')
    return rows


def _load() -> State:
    rows = COMP.store_all()
    raw: dict[str, Any] = {'tasks': {k[5:]: v for k, v in rows.items() if k.startswith('task:')}}
    raw.update((k, v) for k, v in rows.items() if not k.startswith('task:'))
    s = cast(State, raw)  # the stored JSON, in the shapes it was saved in
    s.setdefault('refused', [])
    s.setdefault('drafts', {})
    s.setdefault('polls', {})
    _written.update((k, json.dumps(v, sort_keys=True)) for k, v in _rows(s).items())
    return s


state = _load()


def save() -> None:
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


def key(channel: str, thread_ts: str) -> str:
    return f'{channel}:{thread_ts}'


def key_of(task: Task) -> str:
    """The task's key in state['tasks']: its thread's, unless it shares the thread (reviews of one batch)."""
    return task.get('key') or key(task['channel'], task['thread_ts'])


def tasks() -> dict[str, Task]:
    return state['tasks']


def task_of(channel: str, thread_ts: str) -> Task | None:
    return state['tasks'].get(key(channel, thread_ts))


def review_of(task: Task) -> Review:
    """The PR review a task runs, or {} (a hub ask's `review` is its approve-before-posting flag)."""
    r = task.get('review')
    return r if isinstance(r, dict) else {}


def now_iso() -> str:
    """Now in T3's timestamp format; compared as strings with T3's, so keep the format exact."""
    return datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'


def parse_iso(iso: str | None) -> float:
    return datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp() if iso else 0.0


def new_task(
    channel: str,
    thread_ts: str,
    thread: str,
    title: str,
    outbox: str,
    trigger_ts: str,
    line: Line | None,
    route: Route,
    /,
    **extra: Unpack[Task],
) -> Task:
    """line: its thinking line (tasks.post_line) or None; route: where its chat started and why (projects.route)."""
    now = now_iso()
    t: Task = {
        'thread': thread,
        'title': title,
        'route': route,
        'channel': channel,
        'thread_ts': thread_ts,
        'outbox': outbox,
        'trigger_ts': trigger_ts,
        'line': line,
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
        **extra,
    }
    with lock:
        state['tasks'][key_of(t)] = t
    save()
    return t


def prepare_for_start() -> None:
    """Normalise loaded tasks after a restart (their states: machine.prepare_all)."""
    for t in state['tasks'].values():
        if 'route' not in t:  # saved before routes were recorded (projects.BY 'earlier'): its chat stays where it is
            t['route'] = {
                'project': t.get('project') or default_project(),
                'by': 'earlier',
                'why': 'started before routes',
            }
        t.pop('project', None)
        if {'retries', 'retry_at', 'retry_sent'} & t.keys():  # saved before retries had a state machine (fsm.RETRY)
            due, sent = t.pop('retry_at', None), t.pop('retry_sent', 0)
            t['retry'] = {
                'state': 'waiting' if due else 'idle',
                'count': t.pop('retries', 0) or 0,
                'at': due or sent or 0,
            }
    for p in state['polls'].values():  # saved before polls had a state machine (fsm.POLL)
        if 'state' not in p:
            p['state'] = 'open' if p.pop('open', False) else 'closed'
    for d in state['drafts'].values():  # saved before drafts had a revising state (fsm.DRAFT)
        if d.pop('revising', False) and d.get('status') == 'posted':
            d['status'] = 'revising'
