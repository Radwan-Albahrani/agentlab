"""The agent's T3: actions via the Accounts bridge over HTTP, progress read from its database (read-only, t3db.py)."""

import json
import re
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any, TypedDict

from sqlalchemy import func, not_, or_, select
from sqlalchemy.orm import Session

from . import t3db
from .config import BRIDGE, log, secret
from .shapes import Json
from .state import parse_iso
from .t3db import Message, Request, Run, Thread, TurnItem, answered_by_message, parent_of, text_of
from .when import say

BRIDGE_KEY = secret('agent-key.txt')


class Reply(TypedDict, total=False):
    """The Accounts bridge's answer: ok, and the result (T3's own JSON) or what went wrong."""

    ok: bool
    result: Any
    error: str
    stderr: str


class Snapshot(TypedDict):
    """A chat's state at a glance (snapshot): its runs, new answers, open questions, workers and pull requests."""

    running: bool
    last_status: str | None
    last_done: str | None
    messages: list[tuple[str, str | None, str | None]]  # (id, created_at, text) of new answers
    requests: list[tuple[str, str | None, Json]]  # (id, kind, its turn item) of questions the chat waits on
    asked: list[Json]  # questions answered by any message (the turn ended on them)
    workers: list[tuple[str, str | None, bool]]  # (thread id, title, running)
    prs: list[Json]
    interrupted_at: str | None


def bridge(path: str, body: Json) -> Reply:
    req = urllib.request.Request(
        BRIDGE + path,
        data=json.dumps(body).encode(),
        method='POST',
        headers={'X-Agent-Key': BRIDGE_KEY, 'Content-Type': 'application/json'},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except ValueError:
            return {'ok': False, 'error': str(e)}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def agent_up() -> bool:
    """The agent answers (it is down while its container restarts)."""
    try:
        with urllib.request.urlopen(BRIDGE + '/health', timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def error_text(res: Reply) -> str:
    return str(res.get('stderr') or res.get('error') or res.get('result') or '')[:300]


def start_thread(project: str, title: str, message: str) -> tuple[str | None, str]:
    """Start a chat -> (thread_id, error); on no answer, looks the chat up by title (T3 may have created it)."""
    asked_at = datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%S')
    res = bridge('/api/t3/start', {'project': project, 'title': title, 'message': message})
    tid = (res.get('result') or {}).get('threadId')
    if tid:
        return tid, ''
    for _ in range(12):
        with t3db.session() as s:
            found = s.scalar(
                select(Thread.thread_id)
                .where(Thread.title == title, Thread.created_at >= asked_at)
                .order_by(Thread.created_at.desc())
                .limit(1)
            )
        if found:
            log('thread found by title after a failed start:', found)
            return found, ''
        time.sleep(5)
    log('thread start failed:', json.dumps(res)[:500])
    return None, error_text(res) or 'no answer from T3'


def send(thread: str, message: str) -> Reply:
    return bridge('/api/t3/send', {'thread': thread, 'message': message})


def answer(thread: str, message: str) -> Reply:
    """Answer the chat's open question box."""
    return bridge('/api/t3/respond', {'thread': thread, 'message': message})


def stop(thread: str) -> Reply:
    return bridge('/api/t3/stop', {'thread': thread})


def release(thread: str) -> Reply:
    """A finished PR review: the agent drops the worktrees of its chat and its workers now, keeping nothing."""
    return bridge('/api/t3/release', {'thread': thread})


def triage(prompt: str) -> Reply:
    """One quick model call on the agent's own provider."""
    return bridge('/api/t3/triage', {'message': prompt})


def _last_runs(s: Session, tids: list[str]) -> dict[str, tuple[str | None, str | None]]:
    """(status, completed_at) of each chat's latest run, an open one first, then by completion: a message sent mid-run
    leaves its own run cancelled. Chats without runs are left out."""
    rn = (
        func.row_number()
        .over(partition_by=Run.thread_id, order_by=(Run.completed_at.is_(None).desc(), Run.completed_at.desc()))
        .label('rn')
    )
    ranked = select(Run.thread_id, Run.status, Run.completed_at, rn).where(Run.thread_id.in_(tids)).subquery()
    rows = s.execute(select(ranked.c.thread_id, ranked.c.status, ranked.c.completed_at).where(ranked.c.rn == 1))
    return {t: (status, done) for t, status, done in rows}


def _payloads(s: Session, tids: list[str]) -> dict[str, Json]:
    return dict(s.execute(select(Thread.thread_id, Thread.payload).where(Thread.thread_id.in_(tids))).all())


def snapshot(tid: str, since_iso: str) -> Snapshot:
    """A chat's current state: runs, new answers, pending questions, workers, PRs."""
    with t3db.session() as s:
        open_run = s.scalar(select(Run.run_id).where(Run.thread_id == tid, Run.completed_at.is_(None)).limit(1))
        msgs = [
            (m, at, text)
            for m, at, text in s.execute(
                select(Message.message_id, Message.created_at, text_of(Message.payload))
                .where(
                    Message.thread_id == tid,
                    Message.role == 'assistant',
                    Message.streaming == 0,
                    Message.created_at > since_iso,
                )
                .order_by(Message.created_at)
            )
        ]
        pending = [
            (rid, kind, bool(by_message))
            for rid, kind, by_message in s.execute(
                select(Request.runtime_request_id, Request.kind, answered_by_message()).where(
                    Request.thread_id == tid, Request.status == 'pending'
                )
            )
        ]
        reqs = [(rid, kind) for rid, kind, by_message in pending if not by_message]
        items: dict[str, Json] = {}
        if pending:
            recent = s.scalars(
                select(TurnItem.payload)
                .where(TurnItem.thread_id == tid, TurnItem.type.like('%request%'))
                .order_by(TurnItem.ordinal.desc())
                .limit(20)
            ).all()
            for rid, _, _ in pending:
                found_item = next((it for it in recent if it.get('requestId') == rid), None)
                if found_item is not None:
                    items[rid] = found_item
        running = select(Run.run_id).where(Run.thread_id == Thread.thread_id, Run.completed_at.is_(None)).exists()
        found = s.execute(
            select(Thread.thread_id, Thread.title, running, Thread.updated_at).where(parent_of(Thread) == tid)
        ).all()
        reported = [
            text or ''
            for text in s.scalars(
                select(text_of(Message.payload)).where(Message.thread_id == tid, Message.role == 'user')
            )
        ]
        workers = [(w, title, bool(r) or _subagent_busy(w, updated, reported)) for w, title, r, updated in found]
        chats = [tid, *(w for w, *_ in workers)]
        last_runs = _last_runs(s, chats)
        last_run = last_runs.get(tid)
        interrupted = [last[1] for t in chats if (last := last_runs.get(t)) and last[0] == 'interrupted' and last[1]]
        payloads = _payloads(s, chats)
        lead = payloads.get(tid)
        prs = list(lead.get('pullRequests') or []) if lead else []
        for w_tid, *_ in workers:
            pl = payloads.get(w_tid)
            if pl:
                prs += pl.get('pullRequests') or []
                if pl.get('branchPullRequest'):
                    prs.append(pl['branchPullRequest'])
    return {
        'running': bool(open_run),
        'last_status': last_run[0] if last_run else None,
        'last_done': last_run[1] if last_run else None,
        'messages': msgs,
        'requests': [(rid, kind, items.get(rid, {})) for rid, kind in reqs],
        'asked': [items.get(rid, {}) for rid, _, by_message in pending if by_message],
        'workers': workers,
        'prs': prs,
        # the newest run (of the chat or a child) a restart cut off and T3 has not resumed yet
        'interrupted_at': max(interrupted) if interrupted else None,
    }


NATIVE_AGENT = re.compile(r'native-thread.*?([0-9a-f]{12,})$')
SUBAGENT_STALE = 20 * 60  # a subagent quiet this long without reporting counts as gone


def _subagent_busy(w_tid: str, updated: str | None, reported: list[str], now: float | None = None) -> bool:
    """A Claude subagent's chat has no T3 runs: it is working until the lead hears its report (by its agent id)."""
    m = NATIVE_AGENT.search(w_tid or '')
    if not m:
        return False
    if any(m.group(1) in text for text in reported):
        return False
    return (now or time.time()) - parse_iso(updated) < SUBAGENT_STALE


STEP_TEXT = {'reasoning': 'text', 'assistant_message': 'text', 'command_execution': 'input', 'dynamic_tool': 'title'}


def _steps_of(s: Session, tids: list[str], limit: int) -> dict[str, list[str]]:
    """Each chat's latest steps, oldest first: what it thought, said and ran, one short line each."""
    rn = func.row_number().over(partition_by=TurnItem.thread_id, order_by=TurnItem.ordinal.desc()).label('rn')
    ranked = (
        select(TurnItem.thread_id, TurnItem.type, TurnItem.status, TurnItem.payload, rn)
        .where(TurnItem.thread_id.in_(tids), TurnItem.type.in_(STEP_TEXT))
        .subquery()
    )
    out: dict[str, list[str]] = {t: [] for t in tids}
    for t, typ, status, payload in s.execute(
        select(ranked.c.thread_id, ranked.c.type, ranked.c.status, ranked.c.payload)
        .where(ranked.c.rn <= limit)
        .order_by(ranked.c.thread_id, ranked.c.rn.desc())
    ):
        text = str(payload.get(STEP_TEXT[typ]) or '').replace('\n', ' ').strip()
        if text:
            out[t].append(f'{typ.replace("_", " ")}{" (failed)" if status == "failed" else ""}: {text[:200]}')
    return out


def _steps(s: Session, tid: str, limit: int) -> list[str]:
    return _steps_of(s, [tid], limit)[tid]


def _local(iso: str | None) -> str:
    """An ISO time from T3 (UTC) as local time, e.g. 1:34 PM."""
    try:
        return say(parse_iso(iso))
    except (TypeError, ValueError):
        return str(iso or '')


def _said(s: Session, tid: str, role: str, limit: int) -> list[tuple[str, str]]:
    """The chat's latest messages of one role, oldest first: (local time, text on one line)."""
    rows = s.execute(
        select(Message.created_at, text_of(Message.payload))
        .where(Message.thread_id == tid, Message.role == role, Message.streaming == 0)
        .order_by(Message.created_at.desc())
        .limit(limit)
    ).all()
    return [(_local(at), ' '.join((text or '').split())) for at, text in reversed(rows)]


def digest(tid: str) -> str:
    """A compact record of a chat for a side answer: what was asked, its progress messages (where the milestones
    are), its latest steps, workers, PRs and open question. Times are local."""
    snap = snapshot(tid, '9999')
    run = open_run_since(tid)
    lines = [
        f'Now: {say()}',
        f'Running: yes, since {_local(run)}'
        if run
        else f'Running: no; last run {snap["last_status"] or "none"} at {_local(snap["last_done"])}',
    ]
    with t3db.session() as s:
        first = s.scalar(
            select(text_of(Message.payload))
            .where(Message.thread_id == tid, Message.role == 'user')
            .order_by(Message.created_at)
            .limit(1)
        )
        if first:
            lines.append(f'The request: {" ".join(first.split("---")[0].split())[:700]}')
        lines += [
            'Messages to it since (oldest first):',
            *(f'- [{at}] {t[:300]}' for at, t in _said(s, tid, 'user', 6)[1:]),
        ]
        lines += [
            'Its progress messages (oldest first):',
            *(f'- [{at}] {t[:300]}' for at, t in _said(s, tid, 'assistant', 12)),
        ]
        lines += ['Its latest steps (oldest first):', *(f'- {x}' for x in _steps(s, tid, 6))]
        worker_steps = _steps_of(s, [w for w, *_ in snap['workers']], 2)
        for w, title, running in snap['workers']:
            last = worker_steps[w]
            lines.append(
                f'Worker "{title}": {"running" if running else "finished"}' + (f'; last: {last[-1]}' if last else '')
            )
    lines += [f'Pull request: {pr.get("url")}' for pr in snap['prs'] if pr.get('url')]
    if snap['requests'] or snap.get('asked'):
        lines.append('It is waiting on an answer to a question it asked.')
    return '\n'.join(lines)


def busy(tid: str) -> bool:
    s = snapshot(tid, '9999')  # skip messages
    return s['running'] or any(r for _, _, r in s['workers'])


def has_open_run(tid: str) -> bool:
    """The chat or one of its T3 child threads is running."""
    children = select(Thread.thread_id).where(Thread.payload[('lineage', 'parentThreadId')].as_string() == tid)
    with t3db.session() as s:
        return bool(
            s.scalar(
                select(Run.run_id)
                .where(Run.completed_at.is_(None), or_(Run.thread_id == tid, Run.thread_id.in_(children)))
                .limit(1)
            )
        )


def open_run_since(tid: str) -> str | None:
    with t3db.session() as s:
        return s.scalar(
            select(Run.requested_at)
            .where(Run.thread_id == tid, Run.completed_at.is_(None))
            .order_by(Run.requested_at)
            .limit(1)
        )


def last_answer(tid: str) -> str:
    with t3db.session() as s:
        text = s.scalar(
            select(text_of(Message.payload))
            .where(Message.thread_id == tid, Message.role == 'assistant', Message.streaming == 0)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
    return text or ''


def waiting_question(tid: str) -> bool:
    """An open question box; a question answered by message just takes the next message."""
    with t3db.session() as s:
        return bool(
            s.scalar(
                select(Request.runtime_request_id)
                .where(
                    Request.thread_id == tid,
                    Request.kind == 'user_input',
                    Request.status == 'pending',
                    not_(answered_by_message()),
                )
                .limit(1)
            )
        )


def run_error(tid: str) -> str:
    """The chat's latest `error` turn item, as T3 wrote it (JSON), or ''."""
    with t3db.session() as s:
        payload = s.scalar(
            select(TurnItem.payload)
            .where(TurnItem.thread_id == tid, TurnItem.type == 'error')
            .order_by(TurnItem.ordinal.desc())
            .limit(1)
        )
    return json.dumps(payload, ensure_ascii=False) if payload else ''
