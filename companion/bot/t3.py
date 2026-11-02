"""The agent behind the companion: actions go through the agent's Accounts-app bridge (`t3 thread ...` over HTTP, locked
with a shared key); progress is read straight from the agent's T3 database, read-only."""

import json
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

from .config import BRIDGE, T3, log, secret

BRIDGE_KEY = secret('agent-key.txt')


def bridge(path, body):
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


def error_text(res):
    return str(res.get('stderr') or res.get('error') or res.get('result') or '')[:300]


def db():
    return sqlite3.connect(f'file:{T3}/statev2.sqlite?mode=ro', uri=True, timeout=5)


def query(sql, args=(), one=False):
    con = db()
    try:
        cur = con.execute(sql, args)
        return cur.fetchone() if one else cur.fetchall()
    finally:
        con.close()


# ---------------------------------------------------------------- actions
def start_thread(project, title, message):
    """Start a chat. T3 can be slow to answer `thread start` (busy event loop) even though the chat was created,
    so a missing answer is followed by a look for the chat by its title. Returns (thread_id, error)."""
    asked_at = datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%S')
    res = bridge('/api/t3/start', {'project': project, 'title': title, 'message': message})
    tid = (res.get('result') or {}).get('threadId')
    if tid:
        return tid, ''
    for _ in range(12):
        row = query(
            """select thread_id from orchestration_v2_projection_threads
                       where title = ? and created_at >= ? order by created_at desc limit 1""",
            (title, asked_at),
            one=True,
        )
        if row:
            log('thread found by title after a failed start:', row[0])
            return row[0], ''
        time.sleep(5)
    log('thread start failed:', json.dumps(res)[:500])
    return None, error_text(res) or 'no answer from T3'


def send(thread, message):
    return bridge('/api/t3/send', {'thread': thread, 'message': message})


def answer(thread, message):
    """Answer the chat's open question box (instead of queueing a message behind it)."""
    return bridge('/api/t3/respond', {'thread': thread, 'message': message})


def stop(thread):
    return bridge('/api/t3/stop', {'thread': thread})


def triage(prompt):
    """One quick model call on the agent's own provider (whatever it is signed in to)."""
    return bridge('/api/t3/triage', {'message': prompt})


# ---------------------------------------------------------------- reading progress
def snapshot(tid, since_iso):
    """Everything the Slack thread needs about a chat (and its workers) right now."""
    with db() as con:
        q = con.execute
        open_run = q(
            'select 1 from orchestration_v2_projection_runs where thread_id = ? and completed_at is null', (tid,)
        ).fetchone()
        # the run that ENDED last decides the outcome: a message sent while a run is busy gets folded into
        # that run and its own run is marked cancelled (earlier), so "newest started" would say "stopped"
        last_run = q(
            """select status, completed_at from orchestration_v2_projection_runs where thread_id = ?
                        order by completed_at is null desc, completed_at desc limit 1""",
            (tid,),
        ).fetchone()
        msgs = q(
            """select message_id, created_at, json_extract(payload_json, '$.text') from orchestration_v2_projection_messages
                    where thread_id = ? and role = 'assistant' and streaming = 0 and created_at > ? order by created_at""",
            (tid, since_iso),
        ).fetchall()
        reqs = q(
            """select runtime_request_id, kind from orchestration_v2_projection_runtime_requests
                    where thread_id = ? and status = 'pending'""",
            (tid,),
        ).fetchall()
        items = {}
        for rid, _ in reqs:
            for (pl,) in q(
                """select payload_json from orchestration_v2_projection_turn_items where thread_id = ?
                              and type like '%request%' order by ordinal desc limit 20""",
                (tid,),
            ):
                it = json.loads(pl)
                if it.get('requestId') == rid:
                    items[rid] = it
                    break
        workers = q(
            """select t.thread_id, t.title,
                              exists(select 1 from orchestration_v2_projection_runs r where r.thread_id = t.thread_id and r.completed_at is null)
                       from orchestration_v2_projection_threads t where coalesce(
                         json_extract(t.payload_json, '$.lineage.parentThreadId'),
                         json_extract(t.payload_json, '$.parentThreadId')) = ?""",
            (tid,),
        ).fetchall()
        row = q('select payload_json from orchestration_v2_projection_threads where thread_id = ?', (tid,)).fetchone()
        prs = list(json.loads(row[0]).get('pullRequests') or []) if row else []
        for w_tid, _, _ in workers:  # PRs opened by its workers count too
            wr = q(
                'select payload_json from orchestration_v2_projection_threads where thread_id = ?', (w_tid,)
            ).fetchone()
            if wr:
                pl = json.loads(wr[0])
                prs += pl.get('pullRequests') or []
                if pl.get('branchPullRequest'):
                    prs.append(pl['branchPullRequest'])
    return {
        'running': bool(open_run),
        'last_status': last_run[0] if last_run else None,
        'last_done': last_run[1] if last_run else None,
        'messages': msgs,
        'requests': [(rid, kind, items.get(rid, {})) for rid, kind in reqs],
        'workers': [(w, t, bool(r)) for w, t, r in workers],
        'prs': prs,
    }


def busy(tid):
    s = snapshot(tid, '9999')  # no messages needed, just the state
    return s['running'] or any(r for _, _, r in s['workers'])


def has_open_run(tid):
    """The chat or one of its T3 child threads is running."""
    return bool(
        query(
            """select 1 from orchestration_v2_projection_runs r where r.completed_at is null and (r.thread_id = ?
                 or r.thread_id in (select thread_id from orchestration_v2_projection_threads
                                    where json_extract(payload_json, '$.lineage.parentThreadId') = ?))""",
            (tid, tid),
            one=True,
        )
    )


def open_run_since(tid):
    row = query(
        """select requested_at from orchestration_v2_projection_runs where thread_id = ? and completed_at is null
                   order by requested_at limit 1""",
        (tid,),
        one=True,
    )
    return row[0] if row else None


def last_answer(tid):
    row = query(
        """select json_extract(payload_json, '$.text') from orchestration_v2_projection_messages
                   where thread_id = ? and role = 'assistant' and streaming = 0 order by created_at desc limit 1""",
        (tid,),
        one=True,
    )
    return row[0] if row else ''


def waiting_question(tid):
    return bool(
        query(
            """select 1 from orchestration_v2_projection_runtime_requests
                         where thread_id = ? and kind = 'user_input' and status = 'pending' limit 1""",
            (tid,),
            one=True,
        )
    )


def run_error(tid):
    """The text of the chat's latest error item (T3 keeps provider failures as an `error` turn item)."""
    row = query(
        """select payload_json from orchestration_v2_projection_turn_items where thread_id = ?
                   and type = 'error' order by ordinal desc limit 1""",
        (tid,),
        one=True,
    )
    return row[0] if row else ''
