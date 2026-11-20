"""The companion's persisted state (tasks keyed by Slack thread, see key_of; polls, drafts...); access it under `lock`."""

import json
import threading
from datetime import UTC, datetime
from typing import Unpack

from pydantic import TypeAdapter

from .config import COMP
from .shapes import Json, Line, Review, Route, State, Task

lock = threading.RLock()
_written: dict[str, str] = {}  # store key -> JSON last written


def _rows(s: State) -> Json:
    """Store rows: task:<key> per task, other top-level keys as themselves."""
    rows: Json = {f'task:{k}': t for k, t in s['tasks'].items()}
    rows.update((k, v) for k, v in s.items() if k != 'tasks')
    return rows


RETIRED = ('first', 'last_summary_at', 'posted')  # task keys nothing writes any more: dropped as they load


def _retire(task: Json) -> Json:
    out = {k: v for k, v in task.items() if k not in RETIRED}
    if isinstance(out.get('review'), bool):  # the hub ask's preview flag, now `preview`
        out['preview'] = out.pop('review')
    if isinstance(out.get('review'), dict):
        out['review'] = {k: v for k, v in out['review'].items() if k != 'card'}
    return out


SHAPE: TypeAdapter[State] = TypeAdapter(State)


def _load() -> State:
    """The stored records, checked against shapes.State: one that doesn't fit stops the companion here."""
    rows = COMP.store_all()
    raw: Json = {'refused': [], 'drafts': {}, 'polls': {}}
    raw.update((k, v) for k, v in rows.items() if not k.startswith('task:'))
    raw['tasks'] = {k[5:]: _retire(v) for k, v in rows.items() if k.startswith('task:')}
    s = SHAPE.validate_python(raw)
    _written.update((k, json.dumps(v, sort_keys=True)) for k, v in rows.items())
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
    """The PR review a task runs, or {}."""
    return task.get('review') or {}


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
