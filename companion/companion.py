"""Bot <-> hub contract. Folder <data>/companions/<name>/ (COMPANION_DATA), mounted into the hub:

companion.db  SQLite (WAL); bot writes, hub reads only; never trimmed. The tables as models: tables.py.
  events(id, at, kind, title, task, "to", detail, ok)   append-only
  tasks(id, title, kind, requester, status, waiting, outcome, started, ended, thread, slack, source, updated,
        resumes_at, started_by, via, approved_by, party, phase, case_link, project, route_by, route_why) upserted,
        never deleted. project: the T3 project its chat started in; route_by: why (bot/projects.py BY: repo | named |
        channel | thread | topic | default | checkout | earlier); route_why: the evidence, for people.
    kind: task | errand | review. party: owner | colleague | errand (who the conversation is with).
    phase: the task's state machine (bot/machine.py): working | waiting_owner | waiting_answer | paused | answered |
      nothing_to_do | stopped | failed. case_link: the owner's case thread in Slack ('' without a case).
    The audit: started_by (a name; '' = the owner), via (how: "in #general", "in a DM", "from the hub", "in the
      requests channel"...), approved_by (a name, when someone approved it before it started).
    status: working | waiting ("waiting" says for what) | paused (usage limit; resumes_at: epoch or '') | done |
      failed | stopped
  items(id, task, seq, kind, state, at, data, updated)   upserted; the ledger (bot/ledger.py): every message in and
    out of a task and everything waiting on the owner. kind: in | final | message | edit | approval | credential |
    poll_change. state: that kind's state machine. data JSON (bot/ledger.py SHOWN): by, to, label, text, files,
    private, note, ref, action, details, side, question, where, held, history [[state, at, note]].
  polls(id, task, open, closes, data, updated)   upserted; data JSON: question, channel,
    link, multiple, closed, options [{label, votes, voters [{name, avatar}]}]
  pulls(id, repo, number, updated, data)   replaced on each re-read;
    data JSON: title, url, author, avatar, labels, additions, deletions, ci, review (latest)
  store(key, value, updated)   bot's own state as JSON; hub ignores it
heartbeat.json        {"name", "agent", "at", "since", "connected", "mode", "workspace", "channels", "people", "github"};
                      channels: [{"id", "name", "member"}] (member: bot can post);
                      people: [{"id", "name", "avatar"}] the options of "people" settings;
                      github: {"ready", "bot", "accounts", "at", "error", "people": [{"login", "avatar"}]}
settings-schema.json  [{"key", "label", "help", "type": "choice"|"bool"|"text"|"people"|"links",
                        "options": [{"value", "label", "help"}], "default", "when"?: {"<other key>": [values it shows for]}}];
                      people: a list of user ids; links: [{"github": login, "slack": user id}]
                      text may name a "source" ("channels" | "github_people" | "github_repos"): the hub then offers a picker
settings.json         written by the hub; re-read on every setting() call
asks/<id>.json        written by the hub, removed by take_asks:
                      {"type": "ask", "text", "channel" (an id or ""), "review" (bool), "at"}
                      {"type": "poll", "poll", "multiple"?, "closes"? (epoch), "close"?}
                      {"type": "pulls"}: re-read open pull requests
                      {"type": "review", "repo", "number"}: review and QA that pull request"""

import json
import os
import threading
import time
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Engine, create_engine, delete, event, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session, sessionmaker
from tables import CARD, Base, Event, Item, Poll, Pull, Stored, TaskCard

Row = Mapping[str, Any]


def engine_for(path: str) -> Engine:
    """companion.db in WAL mode, shared by the bot's threads; JSON kept readable (no \\u escapes)."""
    engine = create_engine(
        f'sqlite:///{path}',
        connect_args={'check_same_thread': False},
        json_serializer=lambda v: json.dumps(v, ensure_ascii=False),
    )

    @event.listens_for(engine, 'connect')
    def _wal(dbapi_conn: Any, _record: Any) -> None:
        dbapi_conn.execute('pragma journal_mode=wal')  # SQLAlchemy has no API for the journal mode

    return engine


def migrate(engine: Engine) -> None:
    """Create what is missing: new tables, and columns added since an older db was made (never drops anything)."""
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        ops = Operations(MigrationContext.configure(conn))
        for diff in compare_metadata(ops.migration_context, Base.metadata):
            if isinstance(diff, tuple) and diff[0] == 'add_column':
                _, _schema, table, column = diff
                ops.add_column(table, Column(column.name, column.type, server_default=column.server_default))


class Companion:
    def __init__(self, name: str, agent: str, folder: str, schema: Iterable[dict[str, Any]] = ()) -> None:
        self.name, self.agent, self.dir = name, agent, folder
        self.since = time.time()
        self.schema = list(schema)
        self._settings: dict[str, Any] = {}
        self._mtime: float | None = None
        self._cards: dict[str, Any] = {}  # id -> last card written
        self._lock = threading.Lock()
        self.asks_dir = os.path.join(folder, 'asks')
        os.makedirs(self.asks_dir, exist_ok=True)
        self.engine = engine_for(os.path.join(folder, 'companion.db'))
        migrate(self.engine)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)
        self._write('settings-schema.json', self.schema)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """One transaction, committed on success (writes are serialised: SQLite has one writer)."""
        with self._lock, self._sessions.begin() as s:
            yield s

    def _write(self, fname: str, data: Any) -> None:
        tmp = os.path.join(self.dir, fname + '.tmp')
        with open(tmp, 'w') as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, os.path.join(self.dir, fname))

    def setting(self, key: str) -> Any:
        """settings.json value if valid, else the schema default."""
        p = os.path.join(self.dir, 'settings.json')
        try:
            m = os.path.getmtime(p)
            if m != self._mtime:
                with open(p) as f:
                    self._settings, self._mtime = json.load(f), m
        except (OSError, ValueError):
            self._settings, self._mtime = {}, None
        field = next((f for f in self.schema if f['key'] == key), None)
        if field is None:
            raise KeyError(key)
        value = self._settings.get(key, field.get('default'))
        if field['type'] == 'choice' and value not in [o['value'] for o in field.get('options', [])]:
            return field.get('default')
        if field['type'] == 'bool':
            return bool(value)
        if field['type'] == 'people':
            return [str(u) for u in value] if isinstance(value, list) else []
        if field['type'] == 'links':
            pairs = value if isinstance(value, list) else []
            return [
                {'github': str(p['github']).strip(), 'slack': str(p['slack']).strip()}
                for p in pairs
                if isinstance(p, dict) and str(p.get('github') or '').strip() and str(p.get('slack') or '').strip()
            ]
        return value

    def take_asks(self) -> list[dict[str, Any]]:
        """The hub's asks, oldest first; each file is removed as taken."""
        out = []
        for name in sorted(os.listdir(self.asks_dir)):
            if not name.endswith('.json'):  # half-written .tmp
                continue
            path = os.path.join(self.asks_dir, name)
            try:
                with open(path) as f:
                    out.append(json.load(f))
            except ValueError:
                pass
            os.remove(path)
        return out

    def heartbeat(self, **extra: Any) -> None:
        self._write(
            'heartbeat.json',
            {'name': self.name, 'agent': self.agent, 'at': time.time(), 'since': self.since, **extra},
        )

    def _changed(self, prefix: str, rows: Sequence[Row]) -> list[Row]:
        return [r for r in rows if self._cards.get(prefix + r['id']) != r]

    def _remember(self, prefix: str, rows: Sequence[Row]) -> None:
        self._cards.update({prefix + r['id']: dict(r) for r in rows})

    def tasks(self, cards: Sequence[Row]) -> None:
        """Upsert changed task cards."""
        changed = self._changed('', cards)
        if not changed:
            return
        now = time.time()
        with self.session() as s:
            _upsert(s, TaskCard, [{**{k: str(c.get(k) or '') for k in CARD}, 'updated': now} for c in changed])
        self._remember('', changed)

    def items(self, rows: Sequence[Row]) -> None:
        """Upsert changed ledger items ({id, task, seq, kind, state, at, data})."""
        changed = self._changed('item:', rows)
        if not changed:
            return
        now = time.time()
        keys = ('id', 'task', 'seq', 'kind', 'state', 'at', 'data')
        with self.session() as s:
            _upsert(s, Item, [{**{k: r[k] for k in keys}, 'updated': now} for r in changed])
        self._remember('item:', changed)

    def polls(self, polls: Sequence[Row]) -> None:
        """Upsert changed poll cards ({id, task, open, closes, ...rest as data})."""
        changed = self._changed('poll:', polls)
        if not changed:
            return
        now = time.time()
        own = ('id', 'task', 'open', 'closes')
        rows = [
            {
                'id': p['id'],
                'task': p['task'],
                'open': bool(p['open']),
                'closes': p['closes'],
                'data': {k: v for k, v in p.items() if k not in own},
                'updated': now,
            }
            for p in changed
        ]
        with self.session() as s:
            _upsert(s, Poll, rows)
        self._remember('poll:', changed)

    def pulls(self, pulls: Sequence[Row]) -> None:
        """Replace the pull request list ({id, repo, number, updated, ...rest as data}) if anything changed."""
        if self._cards.get('pulls') == pulls:
            return
        own = ('id', 'repo', 'number', 'updated')
        with self.session() as s:
            s.execute(delete(Pull))
            s.add_all(Pull(**{k: p[k] for k in own}, data={k: v for k, v in p.items() if k not in own}) for p in pulls)
        self._cards['pulls'] = [dict(p) for p in pulls]

    def event(
        self, kind: str, title: str, task: str | None = None, to: str | None = None, detail: Any = '', ok: bool = True
    ) -> None:
        with self.session() as s:
            s.add(
                Event(
                    at=time.time(),
                    kind=kind,
                    title=str(title)[:200],
                    task=task,
                    to=to,
                    detail=str(detail or '')[:4000],
                    ok=bool(ok),
                )
            )

    def store_all(self) -> dict[str, Any]:
        with self.session() as s:
            return {r.key: r.value for r in s.scalars(select(Stored))}

    def store_put(self, items: Mapping[str, Any]) -> None:
        if not items:
            return
        now = time.time()
        with self.session() as s:
            _upsert(s, Stored, [{'key': k, 'value': v, 'updated': now} for k, v in items.items()])

    def store_delete(self, keys: Iterable[str]) -> None:
        with self.session() as s:
            s.execute(delete(Stored).where(Stored.key.in_(list(keys))))


def _upsert(s: Session, model: type[Base], rows: list[dict[str, Any]]) -> None:
    """Insert rows, replacing any with the same primary key."""
    stmt = insert(model)
    table = model.__table__
    keys = [c.name for c in table.primary_key]
    s.execute(
        stmt.on_conflict_do_update(
            index_elements=keys, set_={c.name: stmt.excluded[c.name] for c in table.columns if c.name not in keys}
        ),
        rows,
    )
