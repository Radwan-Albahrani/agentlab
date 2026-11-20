"""What the host and the updater ask about this agent's T3 chats, read from its database with the typed models in
t3schema.py. `agent-t3 busy | inflight | worktrees` prints the answer as JSON (the host asks through docker exec)."""

import json
import os
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from t3schema import SETTLED, Run, Thread, in_progress, open_db

DB = os.path.join(os.path.expanduser('~'), '.t3', 'userdata', 'statev2.sqlite')
USAGE = 'usage: agent-t3 busy | inflight | worktrees'

# JSON answers: busy -> bool; inflight -> [[run id, thread id]]; worktrees -> {path: finished at (epoch) | null}
Answer = bool | list[tuple[str, str]] | dict[str, float | None] | None


@contextmanager
def reading(path: str = DB) -> Iterator[Session]:
    """A read-only session on the database; its connection is closed on the way out."""
    engine = open_db(path)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def busy(session: Session) -> bool:
    """Any run in progress: no end time and no finished status."""
    return session.scalar(select(Run.run_id).where(in_progress()).limit(1)) is not None


def inflight(session: Session) -> list[tuple[str, str]]:
    """(run id, thread id) of every run without a finished status, ended or not."""
    rows = session.execute(select(Run.run_id, Run.thread_id).where(Run.status.not_in(SETTLED)))
    return [(run_id, thread_id) for run_id, thread_id in rows]


def _epoch(iso: object) -> float:
    return datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp() if isinstance(iso, str) and iso else 0


def worktrees(session: Session) -> dict[str, float | None]:
    """Per worktree path its chats use: when the last of them finished, or None while one is still live. A path
    goes from finished (the latest end wins) to live and stays live: one live chat keeps the worktree."""
    turns = session.execute(
        select(Run.thread_id, func.max(Run.completed_at), func.count().filter(Run.completed_at.is_(None))).group_by(
            Run.thread_id
        )
    )
    running: set[str] = set()
    last_turn: dict[str, str | None] = {}
    for thread_id, last, unfinished in turns:
        last_turn[thread_id] = last
        if unfinished:
            running.add(thread_id)
    done_since: dict[str, float | None] = {}
    for thread_id, payload, deleted in session.execute(select(Thread.thread_id, Thread.payload, Thread.deleted_at)):
        d = payload or {}
        wt = d.get('worktreePath')
        if not wt:
            continue
        settled, unsettled = _epoch(d.get('settledAt')), _epoch(d.get('unsettledAt'))
        # chats T3 never settles (delegate_task children) count from their last finished turn
        ended = (
            _epoch(deleted or d.get('deletedAt'))
            or _epoch(d.get('archivedAt'))
            or (settled if settled > unsettled else 0)
            or (_epoch(last_turn.get(thread_id) or d.get('updatedAt')) if not settled and not unsettled else 0)
        )
        before = done_since.get(wt, 0.0)
        if thread_id in running or not ended:
            done_since[wt] = None
        elif before is not None:
            done_since[wt] = max(before, ended)
    return done_since


def answer(question: str, path: str = DB) -> Answer:
    """The answer to one question; no database yet means no chats (worktrees: None, nothing known)."""
    if not os.path.exists(path):
        return False if question == 'busy' else [] if question == 'inflight' else None
    with reading(path) as session:
        if question == 'busy':
            return busy(session)
        if question == 'inflight':
            return inflight(session)
        return worktrees(session)


def main(argv: Sequence[str]) -> int:
    if len(argv) != 1 or argv[0] not in ('busy', 'inflight', 'worktrees'):
        print(USAGE, file=sys.stderr)
        return 2
    try:
        got = answer(argv[0], DB)
    except SQLAlchemyError as e:
        print(f'agent-t3: {e}', file=sys.stderr)
        return 1
    print(json.dumps(got))
    return 0
