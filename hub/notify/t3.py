"""Reading an agent's T3 database (statev2.sqlite, opened read-only) for what a ping says."""

import json
import os
import re
from collections.abc import Collection
from datetime import UTC, datetime
from functools import cache
from typing import Any, NamedTuple, TypedDict
from urllib.parse import quote

from sqlalchemy import ColumnElement, Engine, and_, distinct, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .t3schema import Message, Request, Run, Thread, TurnItem, open_db, text_of
from .text import last_question, plain, short

T3 = os.environ.get('NOTIFY_T3', '')  # tests: '<folder>/{id}/...'; otherwise under the agent's own path
Json = dict[str, Any]


def userdata(profile: str) -> str:
    if T3:
        return T3.format(id=profile)
    import cluster  # noqa: PLC0415 - the hub's module; notify also runs in tests without it

    return f'{cluster.agent_dir(profile)}/home/.t3/userdata'


def is_worker() -> ColumnElement[bool]:
    """A chat started through T3's API (subagents, orchestrator workers, companion tasks), not by the owner."""
    return Thread.payload['creationSource'].as_string().in_(('mcp', 'provider'))


def is_subagent() -> ColumnElement[bool]:
    """A subagent's chat: part of its lead's, never a chat of its own."""
    return func.coalesce(Thread.payload[('lineage', 'relationshipToParent')].as_string(), '') == 'subagent'


def engine(profile: str) -> Engine:
    return _engine(f'{userdata(profile)}/statev2.sqlite')


@cache
def _engine(path: str) -> Engine:
    return open_db(path, timeout=3)


def ts(iso: str | None) -> float:
    return datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp() if iso else 0.0


def thread_link(profile: str, tid: str) -> str:
    """A t3code:// link that opens this chat in the T3 iPhone app."""
    try:
        with open(f'{userdata(profile)}/environment-id') as f:
            env = f.read().strip()
    except OSError:
        return ''
    return f't3code://threads/{quote(env, safe="")}/{quote(tid, safe="")}' if env else ''


def newest_chat_link(profile: str) -> str:
    """Link to the agent's most recent owner-started chat, or ''."""
    try:
        with Session(engine(profile)) as s:
            tid = s.scalar(
                select(Thread.thread_id)
                .where(Thread.deleted_at.is_(None), Thread.payload['createdBy'].as_string() == 'user')
                .order_by(Thread.updated_at.desc())
                .limit(1)
            )
    except SQLAlchemyError:
        return ''
    return thread_link(profile, tid) if tid else ''


def last_texts(s: Session, run_ids: Collection[str]) -> dict[str, str]:
    """{run: its last assistant message}, for all of them in one query."""
    if not run_ids:
        return {}
    newest = func.row_number().over(partition_by=Message.run_id, order_by=Message.created_at.desc())
    ranked = (
        select(Message.run_id, text_of(Message.payload).label('text'), newest.label('n'))
        .where(Message.run_id.in_(run_ids), Message.role == 'assistant')
        .subquery()
    )
    return {rid: text or '' for rid, text in s.execute(select(ranked.c.run_id, ranked.c.text).where(ranked.c.n == 1))}


def request_items(s: Session, thread_ids: Collection[str]) -> dict[str, list[Json]]:
    """{chat: its 20 newest request turn items, newest first}, for all of them in one query."""
    if not thread_ids:
        return {}
    newest = func.row_number().over(partition_by=TurnItem.thread_id, order_by=TurnItem.ordinal.desc())
    ranked = (
        select(TurnItem.thread_id, TurnItem.payload, newest.label('n'))
        .where(TurnItem.thread_id.in_(thread_ids), TurnItem.type.like('%request%'))
        .subquery()
    )
    out: dict[str, list[Json]] = {}
    newest_first = select(ranked.c.thread_id, ranked.c.payload).where(ranked.c.n <= 20).order_by(ranked.c.n)
    for tid, payload in s.execute(newest_first):
        if isinstance(payload, dict):
            out.setdefault(tid, []).append(payload)
    return out


def request_item(items: list[Json], rqid: str) -> Json:
    """The turn item holding a question/approval request's questions and options, from its chat's request_items."""
    return next((item for item in items if item.get('requestId') == rqid), {})


def running_chats(s: Session, thread_ids: Collection[str]) -> set[str]:
    """The chats among these with a run that has no end time yet."""
    if not thread_ids:
        return set()
    return set(s.scalars(select(Run.thread_id).where(Run.thread_id.in_(thread_ids), Run.completed_at.is_(None))))


class WorkerRun(NamedTuple):
    project_id: str
    requested_at: str
    going: bool  # no end time, and not cancelled


def worker_runs(s: Session, project_ids: Collection[str], since: str) -> list[WorkerRun]:
    """Runs of worker chats in these projects, requested at `since` or later."""
    if not project_ids:
        return []
    going = and_(Run.completed_at.is_(None), Run.status.not_in(('cancelled',)))
    rows = s.execute(
        select(Thread.project_id, Run.requested_at, going)
        .select_from(Run)
        .join(Thread, Thread.thread_id == Run.thread_id)
        .where(is_worker(), Thread.project_id.in_(project_ids), Run.requested_at >= since)
    )
    return [WorkerRun(project, at, bool(on)) for project, at, on in rows if project is not None and at is not None]


def describe_question(item: Json) -> tuple[str, str]:
    """(headline, details); the headline stays short because iOS previews only ~250 characters."""
    qs = item.get('questions') or []
    if not qs:
        return 'The agent is waiting for your answer.', ''
    head = []
    for n, qq in enumerate(qs):
        tag = qq.get('header') if qq.get('header') not in (None, '', 'Question') else ''
        num = f'{n + 1}/{len(qs)} ' if len(qs) > 1 else ''
        head.append(f'{num}{tag + ": " if tag else ""}{last_question(qq.get("question", ""))}')
        labels = [
            short(re.sub(r'\s*\(Recommended\)', ' (recommended)', o.get('label', '')), 40)
            for o in qq.get('options') or []
        ][:5]
        head += [f'{i + 1}️⃣ {label}' for i, label in enumerate(labels)]
        if labels and qq.get('multiSelect'):
            head.append('(pick one or more)')
    lines, context = [], []
    for qq in qs:
        for i, o in enumerate(qq.get('options') or []):
            desc = o.get('description', '')
            if desc and desc != o.get('label'):
                lines.append(f'{chr(9312 + i)} {short(desc, 80)}')
        if qq.get('multiSelect'):
            lines.append('(pick one or more)')
        q = re.sub(r'\s+', ' ', qq.get('question', '')).strip()
        asked = last_question(q).rstrip('…')
        rest = q.replace(asked, ' ', 1).strip() if asked in q else ''
        if len(rest) > 3:
            context.append(re.sub(r'\s+', ' ', rest))
    if context:
        lines.append('ℹ︎ ' + ' '.join(context))  # noqa: RUF001 - the info emoji, on purpose
    return '\n'.join(head), '\n'.join(lines)


def describe_approval(item: Json) -> tuple[str, str]:
    what = ''
    for k in ('title', 'reason', 'description', 'command', 'input'):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            what = v
            break
        if isinstance(v, (dict, list)) and v:
            what = json.dumps(v)[:400]
            break
    return '', plain(what) or 'The agent wants permission to continue.'


ACTIVE = ('queued', 'preparing', 'starting', 'running', 'waiting')
RECENT_S = 6 * 3600


class Live(TypedDict):
    running: int
    background: int
    waiting: int
    done: int
    failed: int


def live(profile: str, now: float | None = None) -> Live:
    """How busy the agent is, as counts only (never what a chat is about): chats running (the owner's, and background
    ones such as a companion's), waiting on an answer, and finished or failed in the last hours. Subagents don't count
    as chats of their own."""
    now = now or datetime.now(UTC).timestamp()
    out = Live(running=0, background=0, waiting=0, done=0, failed=0)
    cutoff = datetime.fromtimestamp(now - RECENT_S, UTC).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    chats = func.count(distinct(Thread.thread_id))
    worker = is_worker()
    try:
        with Session(engine(profile)) as s:
            active = s.execute(
                select(worker, chats)
                .select_from(Run)
                .join(Thread, Thread.thread_id == Run.thread_id)
                .where(Run.completed_at.is_(None), Run.status.in_(ACTIVE), Thread.deleted_at.is_(None), ~is_subagent())
                .group_by(worker)
            )
            for background, n in active:
                if background:
                    out['background'] += n
                else:
                    out['running'] += n
            out['waiting'] = (
                s.scalar(
                    select(func.count(distinct(Request.thread_id)))
                    .select_from(Request)
                    .join(Thread, Thread.thread_id == Request.thread_id)
                    .where(Request.status == 'pending', Thread.deleted_at.is_(None))
                )
                or 0
            )
            ended = s.execute(
                select(Run.status, chats)
                .select_from(Run)
                .join(Thread, Thread.thread_id == Run.thread_id)
                .where(
                    Run.completed_at > cutoff,
                    Run.status.in_(('completed', 'failed')),
                    Thread.deleted_at.is_(None),
                    ~is_subagent(),
                )
                .group_by(Run.status)
            )
            for status, n in ended:
                if status == 'completed':
                    out['done'] += n
                else:
                    out['failed'] += n
    except SQLAlchemyError:
        pass
    return out
