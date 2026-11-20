"""What companion bots publish (contract: companion/companion.py), read-only except settings.json and asks/."""

import os
import re
import time
import uuid
from collections.abc import Collection, Sequence
from functools import cache
from typing import Any, Literal, NamedTuple, TypedDict

from sqlalchemy import Engine, RowMapping, create_engine, inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

import cluster

from . import secrets as store_secrets
from .companion_tables import CARD, Event, Item, Poll, Pull, TaskCard
from .files import read_json, write_json

ROOT = os.environ.get('COMPANIONS_DIR', '/companions')
LOG_TAIL = 200_000  # bytes
LIVE_WITHIN = 45  # s
TASKS_SHOWN, EVENTS_SHOWN, POLLS_SHOWN = 300, 600, 20

State = Literal['live', 'disconnected', 'offline', 'unconfigured']
Json = dict[str, Any]
Record = dict[str, Any]  # a row's columns over its JSON `data` (keys the bot decides: ledger items, polls, pulls)


class Task(TypedDict):
    """A task card (TaskCard's columns but `updated`) with its ledger items, oldest first."""

    id: str
    title: str
    kind: str
    requester: str
    status: str
    waiting: str
    outcome: str
    started: str
    ended: str
    thread: str
    slack: str
    source: str
    resumes_at: str
    started_by: str
    via: str
    approved_by: str
    party: str
    phase: str
    case_link: str
    project: str
    route_by: str
    route_why: str
    items: list[Record]


class EventRow(TypedDict):
    at: float
    kind: str | None
    title: str | None
    task: str | None
    to: str | None
    detail: str | None
    ok: bool


class Board(NamedTuple):
    """What the bot's database holds, newest first."""

    tasks: list[Task]
    events: list[EventRow]
    polls: list[Record]
    pulls: list[Record]


TemplateUpdate = TypedDict(
    'TemplateUpdate', {'state': str, 'detail': str, 'from': str, 'to': str, 'at': str}, total=False
)


class Companion(TypedDict):
    name: str
    profile: str
    display: str
    url: str
    problem: str
    heartbeat: Json
    state: State
    tasks: list[Task]
    events: list[EventRow]
    polls: list[Record]
    pulls: list[Record]
    template_update: TemplateUpdate


def _folder(name: str) -> str:
    return os.path.join(ROOT, name)


def _state(heartbeat: Json) -> State:
    fresh = time.time() - heartbeat.get('at', 0) < LIVE_WITHIN
    if not fresh:
        return 'offline'
    return 'live' if heartbeat.get('connected') else 'disconnected'


@cache
def _engine(path: str) -> Engine:
    """companion.db read-only, a fresh connection per session (the bot writes it all the time)."""
    return create_engine(f'sqlite:///file:{path}?mode=ro&uri=true', poolclass=NullPool, connect_args={'timeout': 3})


def _task(row: RowMapping, items: list[Record]) -> Task:
    """A card from the columns the bot's database has: an older bot lacks the newer ones, which read as ''."""

    def text(key: str) -> str:
        return str(row.get(key) or '')

    return Task(
        id=text('id'),
        title=text('title'),
        kind=text('kind'),
        requester=text('requester'),
        status=text('status'),
        waiting=text('waiting'),
        outcome=text('outcome'),
        started=text('started'),
        ended=text('ended'),
        thread=text('thread'),
        slack=text('slack'),
        source=text('source'),
        resumes_at=text('resumes_at'),
        started_by=text('started_by'),
        via=text('via'),
        approved_by=text('approved_by'),
        party=text('party'),
        phase=text('phase'),
        case_link=text('case_link'),
        project=text('project'),
        route_by=text('route_by'),
        route_why=text('route_why'),
        items=items,
    )


def _tasks(s: Session, columns: Collection[str], ledger: bool) -> list[Task]:
    """The newest cards, each with its ledger items (loaded for all of them in one query)."""
    shown = [c for key, c in TaskCard.__table__.c.items() if key in CARD and key in columns]
    rows = s.execute(select(*shown).order_by(TaskCard.started.desc()).limit(TASKS_SHOWN)).mappings().all()
    items = _items(s, [str(r['id']) for r in rows]) if ledger else {}
    return [_task(r, items.get(str(r['id']), [])) for r in rows]


def _items(s: Session, task_ids: Sequence[str]) -> dict[str, list[Record]]:
    """{task id: its ledger items, oldest first}: every message in and out and what waits on the owner."""
    if not task_ids:
        return {}
    out: dict[str, list[Record]] = {}
    for it in s.scalars(select(Item).where(Item.task.in_(task_ids)).order_by(Item.task, Item.seq)):
        out.setdefault(it.task, []).append(
            {**(it.data or {}), 'seq': it.seq, 'kind': it.kind, 'state': it.state, 'at': it.at}
        )
    return out


def _events(s: Session) -> list[EventRow]:
    rows = s.scalars(select(Event).order_by(Event.at.desc(), Event.id.desc()).limit(EVENTS_SHOWN))
    return [
        EventRow(at=e.at, kind=e.kind, title=e.title, task=e.task, to=e.to, detail=e.detail, ok=bool(e.ok))
        for e in rows
    ]


def _polls(s: Session) -> list[Record]:
    """Open polls first, then the latest closed ones."""
    rows = s.scalars(select(Poll).order_by(Poll.open.desc(), Poll.closes.desc()).limit(POLLS_SHOWN))
    return [{**p.data, 'id': p.id, 'task': p.task, 'open': bool(p.open), 'closes': p.closes} for p in rows]


def _pulls(s: Session) -> list[Record]:
    """Open pull requests, newest activity first."""
    rows = s.scalars(select(Pull).order_by(Pull.updated.desc()))
    return [{**p.data, 'id': p.id, 'repo': p.repo, 'number': p.number, 'updated': p.updated} for p in rows]


def _read_db(name: str) -> Board:
    """The bot's database, newest first; a table an older bot doesn't have yet reads as []."""
    path = os.path.join(_folder(name), 'companion.db')
    if not os.path.isfile(path):
        return Board([], [], [], [])
    try:
        with Session(_engine(path)) as s:
            schema = inspect(s.connection())
            tables = set(schema.get_table_names())
            columns = {c['name'] for c in schema.get_columns('tasks')} if 'tasks' in tables else set()
            return Board(
                _tasks(s, columns, 'items' in tables) if columns else [],
                _events(s) if 'events' in tables else [],
                _polls(s) if 'polls' in tables else [],
                _pulls(s) if 'pulls' in tables else [],
            )
    except SQLAlchemyError:
        return Board([], [], [], [])


def status(name: str) -> Json:
    """The companion runner's status.json (state, last error), or {}."""
    agent = cluster.companions().get(name, '')
    out: Json = read_json(os.path.join(cluster.agent_dir(agent), 'workspace', '.companion', name, 'status.json'), {})
    return out


def template_update(name: str) -> TemplateUpdate:
    """The last template update agentctl applied (template.json): {state, detail, from, to, at}, or {}."""
    r: Json = read_json(os.path.join(_folder(name), 'template.json'), {})
    if not r:
        return {}
    return {
        'state': r.get('result', ''),
        'detail': r.get('detail', ''),
        'from': r.get('template_from', ''),
        'to': r.get('template_to', ''),
        'at': r.get('at', ''),
    }


def companion(name: str) -> Companion:
    heartbeat: Json = read_json(os.path.join(_folder(name), 'heartbeat.json'), {})
    tasks, events, polls, pulls = _read_db(name)
    st = status(name)
    state: State = 'unconfigured' if st.get('state') == 'not configured' else _state(heartbeat)
    owners = cluster.companions()
    return {
        'name': name,
        'profile': owners[name] if name in owners else str(heartbeat.get('agent', '')),
        'display': cluster.display_name(name),
        'url': url(name),
        'problem': st.get('error') or '',
        'heartbeat': heartbeat,
        'state': state,
        'tasks': tasks,
        'events': events,
        'polls': polls,
        'pulls': pulls,
        'template_update': template_update(name),
    }


def all_companions() -> list[Companion]:
    return [companion(n) for n in cluster.companions()]


def url(name: str) -> str:
    return f'/agents/{cluster.companions().get(name, "")}/{name}'


def settings(name: str) -> list[tuple[Json, Any]]:
    """[(field, current value)] from settings-schema.json and settings.json."""
    schema: list[Json] = read_json(os.path.join(_folder(name), 'settings-schema.json'), [])
    current: Json = read_json(os.path.join(_folder(name), 'settings.json'), {})
    return [(f, current.get(f['key'], f.get('default'))) for f in schema]


def _checked(field: Json, value: Any) -> Any:
    if field['type'] == 'choice' and value not in [o['value'] for o in field.get('options', [])]:
        raise ValueError('Not one of the options.')
    if field['type'] == 'bool':
        return bool(value)
    if field['type'] == 'text':
        return str(value)[:500]
    if field['type'] == 'people':
        if not isinstance(value, list) or not all(isinstance(u, str) and u.isalnum() for u in value):
            raise ValueError('Expected a list of people.')
        return list(dict.fromkeys(value))[:100]
    if field['type'] == 'links':
        return _links(value)
    return value


GITHUB_LOGIN = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$')


def _links(value: Any) -> list[dict[str, str]]:
    """[{github, slack}]: a GitHub login paired with a Slack user id, one pair per login."""
    if not isinstance(value, list):
        raise ValueError('Expected a list of GitHub and Slack pairs.')
    out: dict[str, dict[str, str]] = {}
    for pair in value:
        gh, slack = (pair or {}).get('github', ''), (pair or {}).get('slack', '')
        if not (isinstance(gh, str) and GITHUB_LOGIN.match(gh) and isinstance(slack, str) and slack.isalnum()):
            raise ValueError('Each pair needs a GitHub username and a Slack person.')
        out[gh.lower()] = {'github': gh, 'slack': slack}
    return list(out.values())[:200]


def set_setting(name: str, key: str, value: Any) -> Json:
    """Validate against the schema and write settings.json; returns the field."""
    if name not in cluster.companions():
        raise ValueError('Unknown companion.')
    field = {f['key']: f for f, _ in settings(name)}.get(key)
    if not field:
        raise ValueError('Unknown setting.')
    path = os.path.join(_folder(name), 'settings.json')
    current: Json = read_json(path, {})
    current[key] = _checked(field, value)
    write_json(path, current)
    return field


def channels(name: str) -> list[Json] | None:
    """[{id, name, member}] the bot offers for asks, or None when it takes no asks."""
    heartbeat: Json = read_json(os.path.join(_folder(name), 'heartbeat.json'), {})
    found: list[Json] | None = heartbeat.get('channels')
    return found


def ask(name: str, text: str, channel: str, review: bool) -> None:
    """Drop an ask file for the bot; channel is one it is a member of, or ''."""
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


def log_tail(name: str) -> tuple[str, float]:
    """(end of the companion's log, mtime); ('', 0) before it ever ran."""
    agent = cluster.companions().get(name, '')
    path = os.path.join(cluster.agent_dir(agent), 'workspace', '.companion', name, 'logs', 'companion.log')
    try:
        with open(path, 'rb') as f:
            f.seek(max(0, os.path.getsize(path) - LOG_TAIL))
            return f.read().decode('utf-8', 'replace'), os.path.getmtime(path)
    except OSError:
        return '', 0


def save_secret(name: str, file: str, value: str) -> bool:
    """Set one of the companion's own secrets (created when missing); False if unchanged."""
    path = f'companions/{name}/{file}'
    if path not in store_secrets.secrets_map():
        raise ValueError('Not one of its secrets.')
    exists = path in {s['name'] for s in store_secrets.all_secrets()}
    return store_secrets.save(path, value, create=not exists)


def _drop(name: str, ask: Json) -> None:
    folder = os.path.join(_folder(name), 'asks')
    os.makedirs(folder, exist_ok=True)  # a companion that never got an ask has no folder yet
    write_json(os.path.join(folder, f'{time.time_ns()}-{uuid.uuid4().hex[:6]}.json'), ask)


def pulls_refresh(name: str) -> None:
    _drop(name, {'type': 'pulls', 'at': time.time()})


def channels_refresh(name: str) -> None:
    _drop(name, {'type': 'channels', 'at': time.time()})


def review(name: str, pr_id: str) -> Record:
    """Ask the bot to review one of its listed pull requests ("owner/repo#123")."""
    pr = next((p for p in companion(name)['pulls'] if p['id'] == pr_id), None)
    if not pr:
        raise ValueError('That pull request is not in the list any more; refresh it.')
    _drop(name, {'type': 'review', 'repo': pr['repo'], 'number': pr['number'], 'at': time.time()})
    return pr


def poll_change(name: str, poll: str, b: Json) -> None:
    """Ask the bot to change an open poll: multiple choice, closing time (epoch), or close now."""
    if poll not in {p['id'] for p in companion(name)['polls'] if p['open']}:
        raise ValueError('That poll is not open.')
    change: Json = {'type': 'poll', 'poll': poll}
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
