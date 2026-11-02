"""The polling thread: what happened in each agent's T3 since last time, and which of it is worth a ping.

A job is a top-level chat's burst of runs (an orchestrator wakes once per worker report). It ends after a quiet
settle period with no worker in its project still running, and then pings once: done / stopped, or "reply" when the
agent ended on a question. Delegated worker chats never ping. Pending questions and approvals ping right away."""

import threading
import time

from . import bark
from .settings import load
from .t3 import IS_WORKER, connect, describe_approval, describe_question, last_text, request_item, thread_link, ts
from .text import ends_with_question, first_sentence, last_question, plain, short

POLL = 4
SETTLE = 120  # orchestrator: no new run for this long = done
QUICK_SETTLE = 10  # a chat without workers is done almost at once
PER_THREAD_GAP = 30  # seconds between done/stopped pings for one chat
HOURLY_CAP = 40
KINDS = {  # kind -> (icon, action in the title, Bark level; active = sound + lit screen, passive would be silent)
    'question': ('❓', 'Answer needed', 'timeSensitive'),
    'approval': ('✋', 'Approval needed', 'timeSensitive'),
    'reply': ('💬', 'Reply needed', 'timeSensitive'),
    'failed': ('❌', 'Failed', 'timeSensitive'),
    'done': ('✅', 'Done', 'active'),
    'stopped': ('⏸', 'Stopped', 'active'),
}


class Watcher(threading.Thread):
    def __init__(self, profiles):
        super().__init__(daemon=True)
        self.profiles = profiles  # callable: the agent ids now (agents come and go with cluster.json)
        self.mark = {}  # agent -> (runs watermark, requests watermark)
        self.status = {}  # agent -> 'watching' / error text
        self.jobs = {}  # agent -> {thread: job running or settling}
        self.sent_at = {}  # thread -> last ping
        self.hour = []  # ping times in the last hour

    def run(self):
        bark.load_recent()
        while True:
            for p in self.profiles():
                try:
                    self.check(p)
                    self.status[p] = 'watching'
                except Exception as e:  # agent stopped, DB busy, schema change
                    self.status[p] = f'{type(e).__name__}: {e}'[:120]
            time.sleep(POLL)

    def check(self, p):
        con = connect(p)
        try:
            q = con.execute
            if p not in self.mark:  # start from now: no backlog after a restart
                self.mark[p] = (
                    q("select coalesce(max(completed_at),'') from orchestration_v2_projection_runs").fetchone()[0],
                    q(
                        "select coalesce(max(created_at),'') from orchestration_v2_projection_runtime_requests"
                    ).fetchone()[0],
                )
                return
            s = load()
            run_events, run_mark = self.finished_runs(q, p, s)
            req_events, req_mark = self.new_requests(q, p)
            self.mark[p] = (run_mark, req_mark)  # only once both read cleanly: a failed poll is redone
            events = run_events + req_events
        finally:
            con.close()
        for ev in events:
            self.emit(p, *ev, s=s)

    def finished_runs(self, q, p, s):
        run_mark = self.mark[p][0]
        jobs = self.jobs.setdefault(p, {})
        events = []
        for rid, tid, status, started, done, title, worker, proj_id, proj in q(
            f"""select r.run_id, r.thread_id, r.status, r.requested_at, r.completed_at, t.title, {IS_WORKER},
                           t.project_id, pr.title
                    from orchestration_v2_projection_runs r
                    join orchestration_v2_projection_threads t on t.thread_id = r.thread_id
                    left join projection_projects pr on pr.project_id = t.project_id
                    where r.completed_at > ? order by r.completed_at""",
            (run_mark,),
        ):
            run_mark = max(run_mark, done)
            if worker:
                continue
            if status == 'cancelled':  # you pressed stop: you know already
                jobs.pop(tid, None)
                continue
            job = jobs.setdefault(tid, {'start': started})
            job.update(end=done, rid=rid, status=status, title=title, proj=proj, proj_id=proj_id)
            if status == 'failed':
                events.append(self.outcome(q, tid, jobs.pop(tid), 'failed'))
            elif ends_with_question(last_text(q, rid)) and not self.busy(q, tid, job):
                events.append(self.outcome(q, tid, jobs.pop(tid), 'reply'))
        now = time.time()
        for tid, job in list(jobs.items()):  # settled jobs -> one ping
            if now - ts(job['end']) < self.settle(q, job) or self.busy(q, tid, job):
                continue
            jobs.pop(tid)
            if ends_with_question(last_text(q, job['rid'])):
                events.append(self.outcome(q, tid, job, 'reply'))
            elif ts(job['end']) - ts(job['start']) >= s['min_minutes'] * 60:
                events.append(self.outcome(q, tid, job, 'stopped' if job['status'] == 'interrupted' else 'done'))
        return events, run_mark

    def new_requests(self, q, p):
        req_mark = self.mark[p][1]
        events = []
        for rqid, tid, kind, created, status, title, proj in q(
            """select rq.runtime_request_id, rq.thread_id, rq.kind, rq.created_at, rq.status, t.title, pr.title
                   from orchestration_v2_projection_runtime_requests rq
                   join orchestration_v2_projection_threads t on t.thread_id = rq.thread_id
                   left join projection_projects pr on pr.project_id = t.project_id
                   where rq.created_at > ? order by rq.created_at""",
            (req_mark,),
        ):
            req_mark = max(req_mark, created)
            if status != 'pending':  # already answered
                continue
            item = request_item(q, tid, rqid)
            if kind == 'user_input':
                events.append((tid, 'question', title, proj, *describe_question(item)))
            else:
                events.append((tid, 'approval', title, proj, *describe_approval(item)))
        return events, req_mark

    @staticmethod
    def settle(q, job):
        """Orchestrators are woken once per worker report, so wait longer between their runs."""
        if not job.get('workers'):
            job['workers'] = bool(
                q(
                    f"""select 1 from orchestration_v2_projection_runs r
                                       join orchestration_v2_projection_threads t on t.thread_id = r.thread_id
                                       where t.project_id = ? and r.requested_at >= ? and {IS_WORKER} limit 1""",
                    (job['proj_id'], job['start']),
                ).fetchone()
            )
        return SETTLE if job['workers'] else QUICK_SETTLE

    @staticmethod
    def busy(q, tid, job):
        """The chat has a run going, or workers delegated in its project since the job began are still working."""
        if q(
            'select 1 from orchestration_v2_projection_runs where thread_id = ? and completed_at is null limit 1',
            (tid,),
        ).fetchone():
            return True
        return bool(
            q(
                f"""select 1 from orchestration_v2_projection_runs r
                          join orchestration_v2_projection_threads t on t.thread_id = r.thread_id
                          where r.completed_at is null and r.status not in ('cancelled') and t.project_id = ?
                            and r.requested_at >= ? and {IS_WORKER} limit 1""",
                (job['proj_id'], job['start']),
            ).fetchone()
        )

    @staticmethod
    def outcome(q, tid, job, kind):
        """(thread, kind, chat title, project, headline, details) for a finished job."""
        text = last_text(q, job['rid'])
        if kind == 'reply':
            return tid, 'reply', job['title'], job['proj'], last_question(plain(text, 10**6)), plain(text)
        fallback = 'The run stopped with an error.' if kind == 'failed' else 'Finished.'
        return tid, kind, job['title'], job['proj'], '', plain(text) or fallback

    def emit(self, p, tid, kind, title, proj, head, detail, s):
        if s['muted']:
            return
        now = time.time()
        self.hour[:] = [t for t in self.hour if now - t < 3600]
        if len(self.hour) >= HOURLY_CAP:
            return
        if kind in ('done', 'stopped') and now - self.sent_at.get(tid, 0) < PER_THREAD_GAP:
            return
        self.sent_at[tid] = now
        self.hour.append(now)
        icon, action, level = KINDS[kind]
        bark.send(
            f'{icon} {action} · {p}',
            head or first_sentence(detail),
            short(title, 42),
            level,
            group=p,
            s=s,
            kind=kind,
            profile=p,
            url=thread_link(p, tid),
        )
