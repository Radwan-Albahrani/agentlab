"""The agent's T3: actions via the Accounts bridge over HTTP, progress read from its database (read-only)."""

import json
import re
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

from .config import BRIDGE, T3, log, secret
from .state import parse_iso
from .when import say

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


def agent_up():
    """The agent answers (it is down while its container restarts)."""
    try:
        with urllib.request.urlopen(BRIDGE + '/health', timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


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


def start_thread(project, title, message):
    """Start a chat -> (thread_id, error); on no answer, looks the chat up by title (T3 may have created it)."""
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
    """Answer the chat's open question box."""
    return bridge('/api/t3/respond', {'thread': thread, 'message': message})


def stop(thread):
    return bridge('/api/t3/stop', {'thread': thread})


def triage(prompt):
    """One quick model call on the agent's own provider."""
    return bridge('/api/t3/triage', {'message': prompt})


# A question the agent ends its turn with, answered by a plain message: T3 doesn't wait on it (non-blocking) and
# cancels it once the next message arrives.
REPLY_BY_MESSAGE = "coalesce(json_extract(payload_json, '$.responseCapability.type') = 'message', 0)"


def snapshot(tid, since_iso):
    """A chat's current state: runs, new answers, pending questions, workers, PRs."""
    with db() as con:
        q = con.execute
        open_run = q(
            'select 1 from orchestration_v2_projection_runs where thread_id = ? and completed_at is null', (tid,)
        ).fetchone()
        # by completion, not start: a message sent mid-run leaves its own run cancelled
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
        pending = q(
            f"""select runtime_request_id, kind, {REPLY_BY_MESSAGE} from orchestration_v2_projection_runtime_requests
                    where thread_id = ? and status = 'pending'""",
            (tid,),
        ).fetchall()
        reqs = [(rid, kind) for rid, kind, by_message in pending if not by_message]
        items = {}
        for rid, _, _ in pending:
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
                              exists(select 1 from orchestration_v2_projection_runs r where r.thread_id = t.thread_id and r.completed_at is null),
                              t.updated_at
                       from orchestration_v2_projection_threads t where coalesce(
                         json_extract(t.payload_json, '$.lineage.parentThreadId'),
                         json_extract(t.payload_json, '$.parentThreadId')) = ?""",
            (tid,),
        ).fetchall()
        reported = [
            text or ''
            for (text,) in q(
                """select json_extract(payload_json, '$.text') from orchestration_v2_projection_messages
                     where thread_id = ? and role = 'user'""",
                (tid,),
            )
        ]
        workers = [(w, title, bool(r) or _subagent_busy(w, updated, reported)) for w, title, r, updated in workers]
        interrupted = [
            last[1]
            for t in [tid, *(w for w, *_ in workers)]
            if (
                last := q(
                    """select status, completed_at from orchestration_v2_projection_runs where thread_id = ?
                         order by completed_at is null desc, completed_at desc limit 1""",
                    (t,),
                ).fetchone()
            )
            and last[0] == 'interrupted'
            and last[1]
        ]
        row = q('select payload_json from orchestration_v2_projection_threads where thread_id = ?', (tid,)).fetchone()
        prs = list(json.loads(row[0]).get('pullRequests') or []) if row else []
        for w_tid, *_ in workers:
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
        'asked': [items.get(rid, {}) for rid, _, by_message in pending if by_message],
        'workers': workers,
        'prs': prs,
        # the newest run (of the chat or a child) a restart cut off and T3 has not resumed yet
        'interrupted_at': max(interrupted) if interrupted else None,
    }


NATIVE_AGENT = re.compile(r'native-thread.*?([0-9a-f]{12,})$')
SUBAGENT_STALE = 20 * 60  # a subagent quiet this long without reporting counts as gone


def _subagent_busy(w_tid, updated, reported, now=None):
    """A Claude subagent's chat has no T3 runs: it is working until the lead hears its report (by its agent id)."""
    m = NATIVE_AGENT.search(w_tid or '')
    if not m:
        return False
    if any(m.group(1) in text for text in reported):
        return False
    return (now or time.time()) - parse_iso(updated) < SUBAGENT_STALE


STEP_TEXT = {'reasoning': 'text', 'assistant_message': 'text', 'command_execution': 'input', 'dynamic_tool': 'title'}


def _steps(con, tid, limit):
    """The chat's latest steps, oldest first: what it thought, said and ran, one short line each."""
    out = []
    for typ, status, payload in con.execute(
        """select type, status, payload_json from orchestration_v2_projection_turn_items where thread_id = ?
             and type in ('reasoning', 'assistant_message', 'command_execution', 'dynamic_tool')
           order by ordinal desc limit ?""",
        (tid, limit),
    ):
        text = str(json.loads(payload).get(STEP_TEXT[typ]) or '').replace('\n', ' ').strip()
        if text:
            out.append(f'{typ.replace("_", " ")}{" (failed)" if status == "failed" else ""}: {text[:200]}')
    return out[::-1]


def _local(iso):
    """An ISO time from T3 (UTC) as local time, e.g. 1:34 PM."""
    try:
        return say(parse_iso(iso))
    except (TypeError, ValueError):
        return str(iso or '')


def _said(con, tid, role, limit):
    """The chat's latest messages of one role, oldest first: (local time, text on one line)."""
    rows = con.execute(
        """select created_at, json_extract(payload_json, '$.text') from orchestration_v2_projection_messages
             where thread_id = ? and role = ? and streaming = 0 order by created_at desc limit ?""",
        (tid, role, limit),
    ).fetchall()
    return [(_local(at), ' '.join((text or '').split())) for at, text in reversed(rows)]


def digest(tid):
    """A compact record of a chat for a side answer: what was asked, its progress messages (where the milestones
    are), its latest steps, workers, PRs and open question. Times are local."""
    s = snapshot(tid, '9999')
    run = open_run_since(tid)
    lines = [
        f'Now: {say()}',
        f'Running: yes, since {_local(run)}'
        if run
        else f'Running: no; last run {s["last_status"] or "none"} at {_local(s["last_done"])}',
    ]
    with db() as con:
        first = con.execute(
            """select json_extract(payload_json, '$.text') from orchestration_v2_projection_messages
                 where thread_id = ? and role = 'user' order by created_at limit 1""",
            (tid,),
        ).fetchone()
        if first and first[0]:
            lines.append(f'The request: {" ".join(first[0].split("---")[0].split())[:700]}')
        lines += [
            'Messages to it since (oldest first):',
            *(f'- [{at}] {t[:300]}' for at, t in _said(con, tid, 'user', 6)[1:]),
        ]
        lines += [
            'Its progress messages (oldest first):',
            *(f'- [{at}] {t[:300]}' for at, t in _said(con, tid, 'assistant', 12)),
        ]
        lines += ['Its latest steps (oldest first):', *(f'- {x}' for x in _steps(con, tid, 6))]
        for w, title, running in s['workers']:
            last = _steps(con, w, 2)
            lines.append(
                f'Worker "{title}": {"running" if running else "finished"}' + (f'; last: {last[-1]}' if last else '')
            )
    lines += [f'Pull request: {pr.get("url")}' for pr in s['prs'] if pr.get('url')]
    if s['requests'] or s.get('asked'):
        lines.append('It is waiting on an answer to a question it asked.')
    return '\n'.join(lines)


def busy(tid):
    s = snapshot(tid, '9999')  # skip messages
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
    """An open question box; a question answered by message just takes the next message."""
    return bool(
        query(
            f"""select 1 from orchestration_v2_projection_runtime_requests where thread_id = ?
                  and kind = 'user_input' and status = 'pending' and not {REPLY_BY_MESSAGE} limit 1""",
            (tid,),
            one=True,
        )
    )


def run_error(tid):
    """The chat's latest `error` turn item."""
    row = query(
        """select payload_json from orchestration_v2_projection_turn_items where thread_id = ?
                   and type = 'error' order by ordinal desc limit 1""",
        (tid,),
        one=True,
    )
    return row[0] if row else ''
