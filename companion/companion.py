"""Bot <-> hub contract. Folder <data>/companions/<name>/ (COMPANION_DATA), mounted into the hub:

companion.db  SQLite (WAL); bot writes, hub reads only; never trimmed.
  events(id, at, kind, title, task, "to", detail, ok)   append-only
  tasks(id, title, kind, requester, status, waiting, outcome, started, ended, thread, slack, source, updated)
    upserted, never deleted. kind: task | errand.
    status: working | waiting ("waiting" says for what) | done | failed | stopped
  polls(id, task, open, closes, data, updated)   upserted; data JSON: question, channel,
    link, multiple, closed, options [{label, votes, voters [{name, avatar}]}]
  pulls(id, repo, number, updated, data)   replaced on each re-read;
    data JSON: title, url, author, avatar, labels, additions, deletions, ci, review (latest)
  store(key, value, updated)   bot's own state as JSON; hub ignores it
heartbeat.json        {"name", "agent", "at", "since", "connected", "mode", "workspace", "channels", "people", "github"};
                      channels: [{"id", "name", "member"}] (member: bot can post);
                      people: [{"id", "name", "avatar"}] the options of "people" settings;
                      github: {"ready", "bot", "accounts", "at", "error"}
settings-schema.json  [{"key", "label", "help", "type": "choice"|"bool"|"text"|"people", "options": [{"value", "label", "help"}],
                        "default", "when"?: {"<other key>": [values it shows for]}}]; people: a list of user ids
settings.json         written by the hub; re-read on every setting() call
asks/<id>.json        written by the hub, removed by take_asks:
                      {"type": "ask", "text", "channel" (an id or ""), "review" (bool), "at"}
                      {"type": "poll", "poll", "multiple"?, "closes"? (epoch), "close"?}
                      {"type": "pulls"}: re-read open pull requests
                      {"type": "review", "repo", "number"}: review and QA that pull request"""

import json
import os
import sqlite3
import threading
import time

CARD = (
    'id',
    'title',
    'kind',
    'requester',
    'status',
    'waiting',
    'outcome',
    'started',
    'ended',
    'thread',
    'slack',
    'source',
)
SCHEMA_SQL = f"""
create table if not exists events (id integer primary key, at real not null, kind text, title text, task text, "to" text,
                                   detail text, ok integer not null default 1);
create index if not exists events_at on events (at);
create index if not exists events_kind on events (kind, at);
create table if not exists tasks ({', '.join(c + (' text primary key' if c == 'id' else ' text') for c in CARD)}, updated real);
create index if not exists tasks_started on tasks (started);
create table if not exists store (key text primary key, value text not null, updated real);
create table if not exists polls (id text primary key, task text, open integer, closes real, data text, updated real);
create table if not exists pulls (id text primary key, repo text, number integer, updated text, data text);
"""


class Companion:
    def __init__(self, name, agent, folder, schema=()):
        self.name, self.agent, self.dir = name, agent, folder
        self.since = time.time()
        self.schema = list(schema)
        self._settings, self._mtime = {}, None
        self._cards = {}  # id -> last card written
        self._lock = threading.Lock()
        self.asks_dir = os.path.join(folder, 'asks')
        os.makedirs(self.asks_dir, exist_ok=True)
        self.db = sqlite3.connect(os.path.join(folder, 'companion.db'), check_same_thread=False, isolation_level=None)
        self.db.execute('pragma journal_mode=wal')
        self.db.executescript(SCHEMA_SQL)
        self._write('settings-schema.json', self.schema)

    def _write(self, fname, data):
        tmp = os.path.join(self.dir, fname + '.tmp')
        with open(tmp, 'w') as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, os.path.join(self.dir, fname))

    def setting(self, key):
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
        return value

    def take_asks(self):
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

    def heartbeat(self, **extra):
        self._write(
            'heartbeat.json',
            {'name': self.name, 'agent': self.agent, 'at': time.time(), 'since': self.since, **extra},
        )

    def tasks(self, cards):
        """Upsert changed task cards."""
        changed = [c for c in cards if self._cards.get(c['id']) != c]
        if not changed:
            return
        now = time.time()
        with self._lock:
            self.db.execute('begin')
            self.db.executemany(
                f'insert or replace into tasks ({", ".join(CARD)}, updated) values ({", ".join("?" * len(CARD))}, ?)',
                [(*(str(c.get(k) or '') for k in CARD), now) for c in changed],
            )
            self.db.execute('commit')
        self._cards.update({c['id']: dict(c) for c in changed})

    def polls(self, polls):
        """Upsert changed poll cards ({id, task, open, closes, ...rest as data})."""
        changed = [p for p in polls if self._cards.get('poll:' + p['id']) != p]
        if not changed:
            return
        now = time.time()
        rows = [
            (
                p['id'],
                p['task'],
                int(p['open']),
                p['closes'],
                json.dumps({k: v for k, v in p.items() if k not in ('id', 'task', 'open', 'closes')}),
                now,
            )
            for p in changed
        ]
        with self._lock:
            self.db.execute('begin')
            self.db.executemany('insert or replace into polls values (?, ?, ?, ?, ?, ?)', rows)
            self.db.execute('commit')
        self._cards.update({'poll:' + p['id']: dict(p) for p in changed})

    def pulls(self, pulls):
        """Replace the pull request list ({id, repo, number, updated, ...rest as data}) if anything changed."""
        if self._cards.get('pulls') == pulls:
            return
        rows = [
            (
                p['id'],
                p['repo'],
                p['number'],
                p['updated'],
                json.dumps({k: v for k, v in p.items() if k not in ('id', 'repo', 'number', 'updated')}),
            )
            for p in pulls
        ]
        with self._lock:
            self.db.execute('begin')
            self.db.execute('delete from pulls')
            self.db.executemany('insert into pulls values (?, ?, ?, ?, ?)', rows)
            self.db.execute('commit')
        self._cards['pulls'] = [dict(p) for p in pulls]

    def event(self, kind, title, task=None, to=None, detail='', ok=True):
        with self._lock:
            self.db.execute(
                'insert into events (at, kind, title, task, "to", detail, ok) values (?,?,?,?,?,?,?)',
                (time.time(), kind, str(title)[:200], task, to, str(detail or '')[:500], int(bool(ok))),
            )

    def store_all(self):
        return {k: json.loads(v) for k, v in self.db.execute('select key, value from store')}

    def store_put(self, items):
        if not items:
            return
        now = time.time()
        with self._lock:
            self.db.execute('begin')
            self.db.executemany(
                'insert or replace into store (key, value, updated) values (?, ?, ?)',
                [(k, json.dumps(v, ensure_ascii=False), now) for k, v in items.items()],
            )
            self.db.execute('commit')

    def store_delete(self, keys):
        with self._lock:
            self.db.executemany('delete from store where key = ?', [(k,) for k in keys])
