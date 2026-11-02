"""Tasks: a Slack thread kept in sync with a T3 chat, like a conversation.

start()      a tag (or DM) -> the thread as context -> a new chat in the best-matching project
follow_up()  the owner's next message in that thread -> the chat's next turn (or the answer to its question box;
             a short "status?" while it works is answered from T3 without disturbing it)
tick()       every few seconds per task: one "thinking" line edited live with the current step, milestone lines
             (workers, pull requests), the agent's questions with numbered options, then the answer as a new
             message (Slack notifies on new messages, not on edits). Busy-model failures are retried."""

import re
import time

from . import errands, polls, projects, prompts, slack, t3
from .config import AGENT, COMP, OWNER, SETTLE, STATUS_EVERY, auto_retry, log
from .state import key, lock, new_task, now_iso, parse_iso, save
from .text import first_sentence, mins, no_emoji, without_mention

THINKING = ':seedling: thinking…'


def start(channel, thread_ts, trigger_ts, text, elsewhere=None):
    """elsewhere: (where, messages) of a conversation the companion can't post in (one of the owner's own DMs); the task
    then lives in `channel`, their DM with the companion, with that conversation as its context."""
    k = key(channel, thread_ts)
    slack.react(channel, trigger_ts, 'eyes')
    folder = f'{channel}-{thread_ts.replace(".", "")}'
    msgs = elsewhere[1] if elsewhere else slack.thread_messages(channel, thread_ts, trigger_ts)
    lines, files = slack.transcript(msgs, folder)
    ask = slack.readable(without_mention(text)).strip() or 'Look at this thread and handle it.'
    if elsewhere:
        where = elsewhere[0]
    else:
        where = 'a DM with you' if channel.startswith('D') else f'Slack channel {channel}, thread {thread_ts}'
    chan = slack.channel_name(channel)
    project, why = projects.pick(ask, '\n'.join(lines), chan)
    log('project', project, '-', why)
    title = first_sentence(ask, 70).rstrip('.')
    here = '' if channel.startswith('D') else channel
    member = [c for c in slack.channels() if c['member']]
    open_polls = polls.for_prompt(channel, thread_ts)
    prompt = prompts.task(ask, slack.name(OWNER), where, lines, files, folder, here, member, open_polls)
    tid, err = t3.start_thread(project, title, prompt)
    if not tid:
        slack.post(channel, thread_ts, f":warning: I couldn't start the chat in {AGENT}: {err}")
        slack.react(channel, trigger_ts, 'eyes', remove=True)
        COMP.event('failed', f'Could not start: {title}', task=k, detail=err, ok=False)
        return
    new_task(channel, thread_ts, tid, title, folder, trigger_ts, slack.note_only(channel, thread_ts, THINKING), project)
    log('started', k, tid)
    COMP.event('started', title, task=k, detail=f'task from {slack.name(OWNER)} in ' + (f'#{chan}' if chan else 'a DM'))


# ---------------------------------------------------------------- the owner's next message
STATUS_ASK = re.compile(
    r"\b(status|progress|eta|update me|any update|an update|updates\?|how(?:'s| is) it going|how far"
    r"|where (?:are|r) (?:we|you|u)|done yet|finished yet|what(?:'s| are you| r u) (?:doing|working on|up|happening)"
    r'|still (?:working|going|on it))\b',
    re.I,
)
INSTRUCTION = re.compile(
    r'^\W*(fix|add|change|update|remove|make|move|rename|check|look|use|set|try|run|open|create|delete|revert|test)\b',
    re.I,
)


POLL_WORDS = re.compile(r'\b(poll|vote|votes|voting)\b', re.I)


def is_status_ask(msg):
    """A short "how's it going?", not an instruction that happens to say "status" ("fix the status badge")."""
    return len(msg.split()) <= 8 and not INSTRUCTION.match(msg) and bool(STATUS_ASK.search(msg))


def follow_up(task, text, files, ts):
    ch = task['channel']
    msg = slack.readable(without_mention(text)).strip()
    m = re.fullmatch(r'\s*([1-9])\s*[.)]?\s*', msg)
    if m and m.group(1) in task.get('options', {}):  # "1" answers the last question with option 1
        msg = task['options'][m.group(1)]
    elif is_status_ask(msg) and not files and t3.busy(task['thread']):
        status_reply(task, ts)  # a busy chat would only queue the question
        return
    folder = f'{ch}-{task["thread_ts"].replace(".", "")}'
    paths = slack.download(files, folder)
    between, more = since_last(task, ts, folder)  # untagged messages since the companion last listened
    if between:
        msg = 'Meanwhile in the Slack thread:\n' + '\n'.join(between) + '\n\nMy message now:\n' + msg
        paths += more
    if paths:
        msg += '\n\nFiles (saved for you):\n' + '\n'.join(f'- {p}' for p in paths)
    open_polls = polls.for_prompt(ch, task['thread_ts'])
    if open_polls and POLL_WORDS.search(msg):  # the chat may predate what the companion can do with polls
        msg += '\n\n---' + prompts.poll_changes(prompts.outbox(task['outbox']), slack.name(OWNER), open_polls)
    slack.react(ch, ts, 'eyes')
    res = {}
    if t3.waiting_question(task['thread']):  # answer the question box, don't queue behind it
        res = t3.answer(task['thread'], msg)
        if not res.get('ok'):
            log('respond failed, sending instead:', res.get('result') or res.get('error'))
    if not res.get('ok'):
        res = t3.send(task['thread'], msg)
    if not res.get('ok'):
        slack.react(ch, ts, 'eyes', remove=True)
        slack.post(ch, task['thread_ts'], f":warning: I couldn't pass that on: {t3.error_text(res)}")
        return
    now = now_iso()
    with lock:
        if not task['active']:  # previous turn answered: a fresh thinking line
            task.update(active=True, burst_start=now, step_from=now, status_ts=None, ended='')
        task.update(trigger_ts=ts, seen_ts=ts, quiet_since=0, options={}, last_status='', last_status_at=0)
        if not task.get('status_ts'):
            task.update(status_ts=slack.note_only(ch, task['thread_ts'], THINKING), line_start=time.time())
    save()


def since_last(task, ts, folder):
    """Thread messages between the last one the companion acted on and `ts` (it only acts when tagged, but the chat
    in between is context)."""
    seen = task.get('seen_ts') or task['trigger_ts']
    try:
        msgs = slack.app.client.conversations_replies(
            channel=task['channel'], ts=task['thread_ts'], oldest=seen, limit=200
        )['messages']
    except Exception as e:
        log('since_last failed:', e)
        return [], []
    return slack.transcript([m for m in msgs if seen < m['ts'] < ts], folder)


def status_reply(task, ts):
    """Answer "status?" from T3's own record without queueing a message behind the agent's work."""
    tid = task['thread']
    s = t3.snapshot(tid, task.get('burst_start') or '')
    run = t3.open_run_since(tid)
    since = f' for {mins(time.time() - parse_iso(run))}' if run else ''
    out = [f':hourglass_flowing_sand: **Still working{since}.**']
    last = t3.last_answer(tid)
    if last:
        out.append(f'Latest: {first_sentence(last, 300)}')
    running = [t for _, t, r in s['workers'] if r]
    done = [t for _, t, r in s['workers'] if not r]
    if running:
        out.append(f':jigsaw: Workers running: {", ".join(running[:6])}' + (f' ({len(done)} finished)' if done else ''))
    out += [f':link: <{pr["url"]}|PR #{pr.get("number", "")}>' for pr in s['prs'] if pr.get('url')]
    if s['requests']:
        out.append(":question: It's waiting on your answer to a question above.")
    slack.post(
        task['channel'],
        task['thread_ts'],
        f'Still working{since}',
        md='\n\n'.join(out),
        note="Status from T3 · the agent wasn't interrupted",
    )
    task['seen_ts'] = ts  # don't pass the "status?" on later
    save()


# ---------------------------------------------------------------- following a chat
def question_text(item):
    out, opts, n = [], {}, 0
    for qq in item.get('questions') or []:
        head = qq.get('header') if qq.get('header') not in (None, '', 'Question') else ''
        out.append(f'**{head}:** {qq.get("question", "")}' if head else qq.get('question', ''))
        for o in qq.get('options') or []:
            n += 1
            label, desc = o.get('label', ''), o.get('description', '')
            opts[str(n)] = label
            out.append(f'{n}️⃣ **{label}**' + (f' — {desc}' if desc and desc != label else ''))
    return '\n\n'.join(out) or 'The agent is waiting for your answer.', opts


def working_line(task, s, now):
    """The live 'thinking' message: the agent's current step, plus time and workers on longer jobs."""
    elapsed = now - parse_iso(task['burst_start'])
    running = sum(1 for _, _, r in s['workers'] if r)
    bits = [mins(elapsed)] if elapsed >= 60 else []
    if running:
        bits.append(f'{running} worker{"s" if running > 1 else ""} running')
    step = first_sentence(task.get('latest', '')) if task.get('step_from', '') < task['seen'] else ''
    return f':seedling: {step or "thinking…"}' + (f'  ·  {" · ".join(bits)}' if bits else '')


def reply(task, md, note=None, outcome='answered below'):
    """Post the agent's answer as a NEW message. The thinking line stays where it was, as the record of when
    the companion picked the turn up, closed into one grey line: what happened and for how long."""
    ch, tts = task['channel'], task['thread_ts']
    if task.get('status_ts'):
        elapsed = time.time() - (task.get('line_start') or parse_iso(task.get('burst_start')))  # this line's stretch
        n = task.get('workers_said', 0)
        bits = [
            'Picked this up',
            elapsed >= 60 and f'worked {mins(elapsed)}',
            n and f'{n} worker{"s" if n > 1 else ""}',
            f'{outcome} ↓',
        ]
        line = ':seedling: ' + ' · '.join(b for b in bits if b)
        slack.update(ch, task['status_ts'], no_emoji(line), note=line)
    slack.post(ch, tts, first_sentence(no_emoji(md), 300) or 'Reply', md=md, note=note)
    task['status_ts'] = None


TRANSIENT = re.compile(
    r'at capacity|rate.?limit|too many requests|overloaded|temporarily unavailable|try again later'
    r'|\b(429|500|502|503|504|529)\b|timed? ?out|connection (reset|closed|error)',
    re.I,
)
RETRY_WAITS = (30, 90, 180)  # s before each automatic "continue"


def retry_transient(task, s, now):
    """A run failed on something temporary (model at capacity, rate limit, 5xx): wait, then say "continue", up
    to 3 times. True while a retry is pending, so tick() doesn't report the failure yet."""
    if now - task.get('retry_sent', 0) < 45:  # "continue" sent, the new run is starting
        return True
    if task.get('retry_at'):
        if now < task['retry_at']:
            return True
        task['retry_at'] = None
        if t3.send(task['thread'], 'continue').get('ok'):
            task['retry_sent'] = now
            log('retry sent', task['thread'], task.get('retries'))
            COMP.event(
                'retry',
                f'Model busy, said "continue" ({task.get("retries")}/{len(RETRY_WAITS)})',
                task=key(task['channel'], task['thread_ts']),
                detail=task.get('title', ''),
            )
            return True
        return False
    if (
        not auto_retry()
        or s['last_status'] != 'failed'
        or task.get('retries', 0) >= len(RETRY_WAITS)
        or not TRANSIENT.search(t3.run_error(task['thread']))
    ):
        return False
    n = task['retries'] = task.get('retries', 0) + 1
    wait = RETRY_WAITS[n - 1]
    task['retry_at'] = now + wait
    line = f':hourglass_flowing_sand: The model is busy, so I\'ll say "continue" in {wait} s ({n}/{len(RETRY_WAITS)})'
    if task.get('status_ts'):
        slack.update(task['channel'], task['status_ts'], 'Retrying soon', note=line)
    else:
        task['status_ts'] = slack.note_only(task['channel'], task['thread_ts'], line)
    return True


def resume_if_running(task):
    """A finished task's chat got a new turn from outside Slack (the owner in T3, a wake-up), or its T3 child threads
    are still working: follow it again."""
    if time.time() - parse_iso(task.get('start')) > 3 * 86400 or not t3.has_open_run(task['thread']):
        return False  # only recent chats, to keep the polling cheap
    now = now_iso()
    task.update(
        active=True,
        burst_start=now,
        step_from=now,
        quiet_since=0,
        last_status='',
        last_status_at=0,
        status_ts=None,
        ended='',
    )
    log('following a turn started outside Slack', task['thread'])
    return True


def tick(task):
    if not task['active'] and not resume_if_running(task):
        return
    ch, tts = task['channel'], task['thread_ts']
    s = t3.snapshot(task['thread'], task['seen'])
    now = time.time()
    task['question'] = bool(s['requests'])
    if s['messages']:
        task['seen'] = s['messages'][-1][1]
        task['latest'] = s['messages'][-1][2] or task.get('latest', '')
    _post_questions(task, s)
    _post_milestones(task, s)
    if s['requests']:
        task['quiet_since'] = 0  # waiting for the owner's answer: nothing to show
        return
    if s['running'] or any(r for _, _, r in s['workers']):
        task['quiet_since'] = 0
        if not task.get('status_ts'):  # a new burst after a question / milestone
            task.update(status_ts=slack.note_only(ch, tts, THINKING), line_start=time.time())
        line = working_line(task, s, now)
        if line != task['last_status'] and now - task['last_status_at'] >= STATUS_EVERY:
            slack.update(ch, task['status_ts'], 'thinking…', note=line)
            task.update(last_status=line, last_status_at=now)
        return
    if not task['quiet_since']:
        task['quiet_since'] = now
    # an orchestrator may start more workers right after a run: wait a minute then; a plain chat answers now
    if task['workers_said'] and now - task['quiet_since'] < SETTLE:
        return
    if s['last_status'] == 'interrupted' and now - task['quiet_since'] < 30:
        return  # cut off (a message sent, a restart): a new turn usually follows
    if retry_transient(task, s, now):
        return
    _finish_turn(task, s)


def _post_questions(task, s):
    """The agent asks something formally: post it as its message, with numbered options."""
    for rid, kind, item in s['requests']:
        if rid in task['asked']:
            continue
        task['asked'].append(rid)
        if kind == 'user_input':
            body, opts = question_text(item)
            task['options'] = opts
            dm = task['channel'].startswith('D')
            how = (
                ('Reply with a number or in your own words.' if dm else 'Tag me with a number or your own words.')
                if opts
                else ('Reply in this thread.' if dm else 'Tag me in this thread to answer.')
            )
            reply(task, body, how, 'asked you')
        else:
            reply(task, ':raised_hand: I need your approval for a step.', 'Approve it in the T3 app.', 'needs approval')


def _post_milestones(task, s):
    """Milestones of longer jobs, as short lines of their own."""
    ch, tts = task['channel'], task['thread_ts']
    if len(s['workers']) > task['workers_said']:
        new = [t for _, t, _ in s['workers']][task['workers_said'] :]
        slack.note_only(ch, tts, f':jigsaw: Splitting this up: {", ".join(new[:6])}{"…" if len(new) > 6 else ""}')
        task['workers_said'] = len(s['workers'])
    for pr in s['prs']:
        url = pr.get('url')
        if url and url not in task['prs']:
            task['prs'].append(url)
            snap = pr.get('snapshot') or {}
            draft = ' (draft)' if snap.get('isDraft') else ''
            slack.note_only(
                ch,
                tts,
                f':link: Opened <{url}|PR #{pr.get("number", "")}>{draft}'
                + (f': {snap["title"]}' if snap.get('title') else ''),
            )


REVIEW_NUDGE = (
    'Your T3 child threads have finished. Collect what they found, run the verification step, write qa.md (when QA'
    ' ran) and review.json exactly as your brief says, then end with the one-line summary.'
)


def _finish_turn(task, s):
    r = task.get('review')
    if r and not r.get('published') and s['last_status'] == 'completed' and task.get('nudged', 0) < 2:
        # a lead chat that delegated often ends its turn while the lanes run; when they are done, carry on
        task['nudged'] = task.get('nudged', 0) + 1
        res = t3.send(task['thread'], REVIEW_NUDGE)
        if res.get('ok'):
            task['quiet_since'] = 0
            log('review nudged to finish', r['id'])
            return
    ch, tts = task['channel'], task['thread_ts']
    task['retries'] = 0  # the turn ended for real: next time starts fresh
    final = task.get('latest', '')
    took = parse_iso(s['last_done']) - parse_iso(task['burst_start']) if s['last_done'] else 0
    # footer, Slack style: where it ran and, for longer turns, how long it took
    foot = ' · '.join(
        x for x in (AGENT, (task.get('project') or '').rsplit('/', 1)[-1], took >= 60 and mins(took)) if x
    )
    no_action = re.match(r'\s*`?NO_ACTION:?\s*(.*?)`?\s*$', final or '', re.S)
    status = s['last_status']
    posted = task.pop('posted', False)
    if posted and status == 'completed':  # the post is the answer; the line linking to it is already in the thread
        if task.get('status_ts'):
            slack.update(ch, task['status_ts'], 'Posted', note=':seedling: Picked this up · posted ↓')
        task['status_ts'] = None
        outcome = 'posted'
    elif task.get('requester') and no_action:  # a request that needs nothing: close quietly
        if task.get('status_ts'):
            slack.update(
                ch,
                task['status_ts'],
                'Nothing for me to do',
                note=f':white_check_mark: Nothing for me to do: {no_action.group(1).strip()[:200]}',
            )
        task['status_ts'] = None
        errands.close_head(task, ':white_check_mark: Nothing needed', 'white_check_mark')
        outcome = 'nothing needed'
    elif status == 'failed':
        reply(task, ':x: **That failed.**\n\n' + final, foot, 'failed')
        outcome = 'failed'
    elif status == 'cancelled':
        reply(task, ':black_square_for_stop: Stopped.', foot, 'stopped')
        outcome = 'stopped'
    else:
        reply(task, final or '_(no reply)_', foot)
        outcome = 'answered'
    if task.get('reply_pending') and status == 'completed':  # approved change done -> answer the requester
        errands.reply_requester(task, task.pop('reply_pending'), approved=True)
    slack.react(ch, task['trigger_ts'], 'eyes', remove=True)
    COMP.event(
        'failed' if outcome == 'failed' else 'finished',
        f'{task.get("title", "")[:80]}: {outcome}',
        task=key(ch, tts),
        detail=first_sentence(no_emoji(final), 300),
        ok=outcome != 'failed',
    )
    task.update(active=False, quiet_since=0, last_status='', last_status_at=0, outcome=outcome, ended=now_iso())
