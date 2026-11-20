"""The polling thread: reads each agent's T3 database and pings once per finished top-level job or pending request."""

import threading
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Any, Literal, NamedTuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import bark
from .settings import load
from .t3 import (
    WorkerRun,
    describe_approval,
    describe_question,
    engine,
    is_worker,
    last_texts,
    request_item,
    request_items,
    running_chats,
    thread_link,
    ts,
    worker_runs,
)
from .t3schema import Project, Request, Run, Thread
from .text import ends_with_question, first_sentence, last_question, plain, short

POLL = 4
SETTLE = 120  # s without a new run before an orchestrator's job is done
QUICK_SETTLE = 10
PER_THREAD_GAP = 30
HOURLY_CAP = 40
Kind = Literal['question', 'approval', 'reply', 'failed', 'done', 'stopped']
Outcome = Literal['reply', 'failed', 'done', 'stopped']
KINDS: dict[Kind, tuple[str, str, str]] = {  # kind -> (icon, action in the title, Bark level)
    'question': ('❓', 'Answer needed', 'timeSensitive'),
    'approval': ('✋', 'Approval needed', 'timeSensitive'),
    'reply': ('💬', 'Reply needed', 'timeSensitive'),
    'failed': ('❌', 'Failed', 'timeSensitive'),
    'done': ('✅', 'Done', 'active'),
    'stopped': ('⏸', 'Stopped', 'active'),
}


@dataclass
class Job:
    """A top-level chat at work: from its first finished run until it pings (or a run of it is cancelled)."""

    start: str | None  # when its first run was requested
    end: str = ''  # when its latest run finished
    rid: str = ''
    status: str | None = None
    title: str | None = None
    proj: str | None = None
    proj_id: str | None = None
    workers: bool = False  # orchestrator: worker chats ran in its project since it began


class Finished(NamedTuple):
    """A run that finished since the last poll, with its chat and project."""

    rid: str
    tid: str
    status: str | None
    started: str | None
    done: str | None
    title: str | None
    worker: bool | None
    proj_id: str | None
    proj: str | None


class Ping(NamedTuple):
    tid: str
    kind: Kind
    title: str | None
    proj: str | None
    head: str
    detail: str


@dataclass(frozen=True)
class Reads:
    """What one poll needs to judge its jobs, read with a query per kind (never one per job)."""

    texts: dict[str, str]  # run -> its last assistant message
    running: set[str]  # chats with a run that has no end time yet
    workers: list[WorkerRun]  # worker runs in the jobs' projects since the oldest job began

    @classmethod
    def of(cls, db: Session, jobs: dict[str, Job], runs: Collection[Finished]) -> 'Reads':
        """For the jobs so far ({chat: job}) and the runs that finished since (they start or update jobs)."""
        spans = [(j.proj_id, j.start) for j in jobs.values()] + [(r.proj_id, r.started) for r in runs]
        known = [(p, start) for p, start in spans if p is not None and start is not None]
        return cls(
            texts=last_texts(db, {j.rid for j in jobs.values()} | {r.rid for r in runs}),
            running=running_chats(db, set(jobs) | {r.tid for r in runs}),
            workers=worker_runs(db, {p for p, _ in known}, min(start for _, start in known)) if known else [],
        )

    def text(self, rid: str) -> str:
        return self.texts.get(rid, '')

    def ran(self, job: Job, *, running: bool) -> bool:
        """A worker chat in the job's project had a run since the job began (`running`: one still going)."""
        if job.proj_id is None or job.start is None:
            return False
        start = job.start
        return any(
            w.project_id == job.proj_id and w.requested_at >= start and (w.going or not running) for w in self.workers
        )

    def busy(self, tid: str, job: Job) -> bool:
        """The chat, or a worker in its project since the job began, still has a run going."""
        return tid in self.running or self.ran(job, running=True)

    def settle(self, job: Job) -> int:
        """Seconds of quiet before a job is done: longer for orchestrators, woken once per worker report."""
        if not job.workers:
            job.workers = self.ran(job, running=False)
        return SETTLE if job.workers else QUICK_SETTLE


class Watcher(threading.Thread):
    def __init__(self, profiles: Callable[[], list[str]]) -> None:
        super().__init__(daemon=True)
        self.profiles = profiles  # the current agent ids
        self.mark: dict[str, tuple[str, str]] = {}  # agent -> (runs watermark, requests watermark)
        self.status: dict[str, str] = {}
        self.jobs: dict[str, dict[str, Job]] = {}  # agent -> {thread: job running or settling}
        self.sent_at: dict[str, float] = {}
        self.hour: list[float] = []

    def run(self) -> None:
        bark.load_recent()
        while True:
            for p in self.profiles():
                try:
                    self.check(p)
                    self.status[p] = 'watching'
                except Exception as e:
                    self.status[p] = f'{type(e).__name__}: {e}'[:120]
            time.sleep(POLL)

    def check(self, p: str) -> None:
        with Session(engine(p)) as db:
            if p not in self.mark:  # start from now: no backlog
                self.mark[p] = (
                    db.scalar(select(func.coalesce(func.max(Run.completed_at), ''))) or '',
                    db.scalar(select(func.coalesce(func.max(Request.created_at), ''))) or '',
                )
                return
            s = load()
            run_events, run_mark = self.finished_runs(db, p, s)
            req_events, req_mark = self.new_requests(db, p)
            self.mark[p] = (run_mark, req_mark)  # only once both read cleanly: a failed poll is redone
            events = run_events + req_events
        for ev in events:
            self.emit(p, ev, s)

    def finished_runs(self, db: Session, p: str, s: dict[str, Any]) -> tuple[list[Ping], str]:
        run_mark = self.mark[p][0]
        jobs = self.jobs.setdefault(p, {})
        events = []
        query = (
            select(
                Run.run_id,
                Run.thread_id,
                Run.status,
                Run.requested_at,
                Run.completed_at,
                Thread.title,
                is_worker(),
                Thread.project_id,
                Project.title,
            )
            .select_from(Run)
            .join(Thread, Thread.thread_id == Run.thread_id)
            .outerjoin(Project, Project.project_id == Thread.project_id)
            .where(Run.completed_at > run_mark)
            .order_by(Run.completed_at)
        )
        runs = [Finished(*row) for row in db.execute(query)]
        reads = Reads.of(db, jobs, [r for r in runs if not r.worker and r.status != 'cancelled'])
        for r in runs:
            run_mark = max(run_mark, r.done or '')
            if r.worker:
                continue
            if r.status == 'cancelled':
                jobs.pop(r.tid, None)
                continue
            job = jobs.setdefault(r.tid, Job(start=r.started))
            job.end, job.rid, job.status, job.title, job.proj, job.proj_id = (
                r.done or '',
                r.rid,
                r.status,
                r.title,
                r.proj,
                r.proj_id,
            )
            if r.status == 'failed':
                events.append(self.outcome(reads, r.tid, jobs.pop(r.tid), 'failed'))
            elif ends_with_question(reads.text(r.rid)) and not reads.busy(r.tid, job):
                events.append(self.outcome(reads, r.tid, jobs.pop(r.tid), 'reply'))
        now = time.time()
        for tid, job in list(jobs.items()):
            if now - ts(job.end) < reads.settle(job) or reads.busy(tid, job):
                continue
            jobs.pop(tid)
            if ends_with_question(reads.text(job.rid)):
                events.append(self.outcome(reads, tid, job, 'reply'))
            elif ts(job.end) - ts(job.start) >= s['min_minutes'] * 60:
                events.append(self.outcome(reads, tid, job, 'stopped' if job.status == 'interrupted' else 'done'))
        return events, run_mark

    def new_requests(self, db: Session, p: str) -> tuple[list[Ping], str]:
        req_mark = self.mark[p][1]
        events = []
        query = (
            select(
                Request.runtime_request_id,
                Request.thread_id,
                Request.kind,
                Request.created_at,
                Request.status,
                Thread.title,
                Project.title,
            )
            .select_from(Request)
            .join(Thread, Thread.thread_id == Request.thread_id)
            .outerjoin(Project, Project.project_id == Thread.project_id)
            .where(Request.created_at > req_mark)
            .order_by(Request.created_at)
        )
        requests = db.execute(query).all()
        items = request_items(db, {r.thread_id for r in requests if r.status == 'pending'})
        for rqid, tid, kind, created, status, title, proj in requests:
            req_mark = max(req_mark, created or '')
            if status != 'pending':
                continue
            item = request_item(items.get(tid, []), rqid)
            if kind == 'user_input':
                events.append(Ping(tid, 'question', title, proj, *describe_question(item)))
            else:
                events.append(Ping(tid, 'approval', title, proj, *describe_approval(item)))
        return events, req_mark

    @staticmethod
    def outcome(reads: Reads, tid: str, job: Job, kind: Outcome) -> Ping:
        text = reads.text(job.rid)
        if kind == 'reply':
            return Ping(tid, 'reply', job.title, job.proj, last_question(plain(text, 10**6)), plain(text))
        fallback = 'The run stopped with an error.' if kind == 'failed' else 'Finished.'
        return Ping(tid, kind, job.title, job.proj, '', plain(text) or fallback)

    def emit(self, p: str, ping: Ping, s: dict[str, Any]) -> None:
        if s['muted']:
            return
        now = time.time()
        self.hour[:] = [t for t in self.hour if now - t < 3600]
        if len(self.hour) >= HOURLY_CAP:
            return
        if ping.kind in ('done', 'stopped') and now - self.sent_at.get(ping.tid, 0) < PER_THREAD_GAP:
            return
        self.sent_at[ping.tid] = now
        self.hour.append(now)
        icon, action, level = KINDS[ping.kind]
        bark.send(
            f'{icon} {action} · {p}',
            ping.head or first_sentence(ping.detail),
            short(ping.title or '', 42),
            level,
            group=p,
            s=s,
            kind=ping.kind,
            profile=p,
            url=thread_link(p, ping.tid),
        )
