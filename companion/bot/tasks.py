"""Tasks: a Slack thread kept in sync with a T3 chat (start, follow_up, tick)."""

import re
import time

from . import errands, jobs, limits, polls, projects, prompts, slack, t3
from .config import AGENT, COMP, OWNER, SETTLE, STATUS_EVERY, auto_retry, log
from .state import key, key_of, lock, new_task, now_iso, parse_iso, review_of, save
from .text import first_sentence, hour, mins, no_emoji

THINKING = ':seedling: thinking…'


def quiet(task):
    """A PR review: its progress shows on the batch card (reviews.py), so its thread gets only questions."""
    return bool(review_of(task))


def start(channel, thread_ts, trigger_ts, text, elsewhere=None, guest=None):
    """elsewhere: (where, messages) of a conversation the bot can't post in; guest: who asked, if not the owner."""
    k = key(channel, thread_ts)
    slack.react(channel, trigger_ts, 'eyes')
    folder = f'{channel}-{thread_ts.replace(".", "")}'
    msgs = elsewhere[1] if elsewhere else slack.thread_messages(channel, thread_ts, trigger_ts)
    lines, files = slack.transcript(msgs, folder)
    ask = slack.ask(text).strip() or 'Look at this thread and handle it.'
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
    asker = slack.name(guest or OWNER)
    fresh = not elsewhere and thread_ts == trigger_ts
    prompt = prompts.task(
        ask, slack.name(OWNER), where, lines, files, folder, here, member, open_polls, guest and asker, fresh
    )
    tid, err = t3.start_thread(project, title, prompt)
    if not tid:
        slack.post(channel, thread_ts, f":warning: I couldn't start the chat in {AGENT}: {err}")
        slack.react(channel, trigger_ts, 'eyes', remove=True)
        COMP.event('failed', f'Could not start: {title}', task=k, detail=err, ok=False)
        return
    status = slack.note_only(channel, thread_ts, THINKING)
    new_task(channel, thread_ts, tid, title, folder, trigger_ts, status, project, **({'guest': guest} if guest else {}))
    log('started', k, tid, 'for', guest or 'owner')
    COMP.event('started', title, task=k, detail=f'task from {asker} in ' + (f'#{chan}' if chan else 'a DM'))


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
    """A short "how's it going?", not an instruction mentioning status ("fix the status badge")."""
    return len(msg.split()) <= 8 and not INSTRUCTION.match(msg) and bool(STATUS_ASK.search(msg))


def follow_up(task, text, files, ts, by=None):
    ch = task['channel']
    msg = slack.ask(text).strip()
    m = re.fullmatch(r'\s*([1-9])\s*[.)]?\s*', msg)
    if m and m.group(1) in task.get('options', {}):  # "1" picks option 1 of the last question
        msg = task['options'][m.group(1)]
    elif is_status_ask(msg) and not files and t3.busy(task['thread']):
        status_reply(task, ts)
        return
    if task.get('guest') or (by and by != OWNER):
        msg = f'{slack.name(by or OWNER)}: {msg}'
    folder = f'{ch}-{task["thread_ts"].replace(".", "")}'
    paths = slack.download(files, folder)
    between, more = ([], []) if quiet(task) else since_last(task, ts, folder)  # a batch thread mixes reviews
    if between:
        msg = 'Meanwhile in the Slack thread:\n' + '\n'.join(between) + '\n\nMy message now:\n' + msg
        paths += more
    if paths:
        msg += '\n\nFiles (saved for you):\n' + '\n'.join(f'- {p}' for p in paths)
    open_polls = polls.for_prompt(ch, task['thread_ts'])
    if open_polls and POLL_WORDS.search(msg):
        msg += '\n\n---' + prompts.poll_changes(prompts.outbox(task['outbox']), slack.name(OWNER), open_polls)
    slack.react(ch, ts, 'eyes')
    res = {}
    if t3.waiting_question(task['thread']):
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
        if not task['active']:
            task.update(active=True, burst_start=now, step_from=now, status_ts=None, ended='')
        task.update(
            trigger_ts=ts, seen_ts=ts, quiet_since=0, options={}, question=False, last_status='', last_status_at=0
        )
        if not task.get('status_ts') and not quiet(task):
            task.update(status_ts=slack.note_only(ch, task['thread_ts'], THINKING), line_start=time.time())
    save()


def since_last(task, ts, folder):
    """Transcript of thread messages since the last one acted on, up to `ts`."""
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
    """Answer "status?" from T3's record without messaging the busy chat."""
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
    task['seen_ts'] = ts  # keeps the "status?" out of since_last
    save()


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
    """Text of the live 'thinking' line."""
    elapsed = now - parse_iso(task['burst_start'])
    running = sum(1 for _, _, r in s['workers'] if r)
    bits = [mins(elapsed)] if elapsed >= 60 else []
    if running:
        bits.append(f'{running} worker{"s" if running > 1 else ""} running')
    step = first_sentence(task.get('latest', '')) if task.get('step_from', '') < task['seen'] else ''
    return f':seedling: {step or "thinking…"}' + (f'  ·  {" · ".join(bits)}' if bits else '')


def reply(task, md, note=None, outcome='answered below'):
    """Post the answer as a new message (Slack notifies on new messages, not edits) and close the thinking line."""
    ch, tts = task['channel'], task['thread_ts']
    r = review_of(task)
    if r:  # reviews of a batch share its thread
        md = f':mag: **<{r["url"]}|{r["id"]}>**\n{md}'
    if task.get('status_ts'):
        elapsed = time.time() - (task.get('line_start') or parse_iso(task.get('burst_start')))
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
RETRY_WAITS = (30, 90, 180)  # seconds before each automatic "continue"


def retry_transient(task, s, now):
    """Send "continue" after a transient failure, up to 3 times; True while a retry is pending."""
    if now - task.get('retry_sent', 0) < 45:
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
                task=key_of(task),
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
    elif not quiet(task):
        task['status_ts'] = slack.note_only(task['channel'], task['thread_ts'], line)
    return True


LIMIT_GRACE = 15 * 60  # after the reset, T3's own resume gets this long before Leafy says "continue"
LIMIT_UNKNOWN = 5 * 3600  # no reset time given: the 5-hour window at most
LIMIT_NOTICE = 200  # longer answers are real work that mentions limits, not the notice itself


def _notice(task, now=None):
    """The chat's last answer, when all it says is the limit notice ("You've hit your 5-hour limit · resets …")."""
    latest = task.get('latest') or ''
    return limits.parse(latest, now) if len(latest) <= LIMIT_NOTICE else (False, None)


def limit_hit(task, s):
    """(True, reset epoch or None) when the chat's last run stopped on a usage limit."""
    if s['last_status'] == 'failed':
        hit, at = limits.from_error(t3.run_error(task['thread']))
        return (hit, at) if hit else _notice(task)
    return _notice(task) if s['last_status'] == 'completed' else (False, None)


def paused_line(resumes_at):
    when = f'at {hour(resumes_at)}' if resumes_at else 'when it resets'
    return f':double_vertical_bar: Paused for the usage limit · T3 picks it up again {when}'


def pause(task, resumes_at, run, now):
    """Wait for T3 to resume the chat at the reset: no retries, no failure."""
    first = not task.get('paused')
    task['paused'] = {'at': now, 'resumes_at': resumes_at, 'run': run, 'nudged': 0}
    task.update(retry_at=None, retries=0)
    line = paused_line(resumes_at)
    if task.get('status_ts') and not quiet(task):
        slack.update(task['channel'], task['status_ts'], 'Paused for the usage limit', note=line)
    elif not quiet(task):
        task['status_ts'] = slack.note_only(task['channel'], task['thread_ts'], line)
    if first:
        log('paused for the usage limit', task['thread'], resumes_at)
        COMP.event(
            'paused',
            f'Paused for the usage limit: {task.get("title", "")[:80]}',
            task=key_of(task),
            detail=f'resumes at {hour(resumes_at)}' if resumes_at else 'resumes when the limit resets',
        )


def unpause(task):
    if task.pop('paused', None):
        task.update(last_status='', last_status_at=0)
        log('resumed after the usage limit', task['thread'])


def hold_for_limit(task, s, now):
    """True while a usage-limited chat waits for T3 to resume it (or once that wait has been closed)."""
    p = task.get('paused')
    if p and p['run'] == s['last_done']:  # nothing ran since the pause
        due = (p['resumes_at'] or p['at'] + LIMIT_UNKNOWN) + LIMIT_GRACE
        if now < due:
            return True
        if not p['nudged'] and t3.send(task['thread'], 'continue').get('ok'):
            p['nudged'] = now
            COMP.event('retry', 'The usage limit reset but T3 did not resume: said "continue"', task=key_of(task))
            return True
        if p['nudged'] and now - p['nudged'] < LIMIT_GRACE:
            return True
        task.pop('paused')
        _finish_turn(task, s)
        return True
    hit, resumes_at = limit_hit(task, s)
    if not hit:
        unpause(task)
        return False
    pause(task, resumes_at, s['last_done'], now)
    return True


def recover_limited(task, now):
    """A review that ended as failed on a usage limit (before limits were told apart): paused again instead."""
    if task.get('active') or task.get('outcome') != 'failed' or task.get('limit_checked'):
        return False
    task['limit_checked'] = True
    if now - parse_iso(task.get('ended')) > 86400:
        return False
    hit, resumes_at = _notice(task, now)
    if not hit:
        hit, resumes_at = limits.from_error(t3.run_error(task['thread']), now)
    if not hit:
        return False
    s = t3.snapshot(task['thread'], '9999')  # skip messages
    task.update(active=True, outcome='', ended='', closed='', quiet_since=0)
    pause(task, resumes_at, s['last_done'], now)
    return True


def resume_if_running(task):
    """Reactivate a finished task (under 3 days old) whose chat is running again."""
    if time.time() - parse_iso(task.get('start')) > 3 * 86400 or not t3.has_open_run(task['thread']):
        return False
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
    task['question'] = bool(s['requests'] or s.get('asked'))
    if s['messages']:
        task['seen'] = s['messages'][-1][1]
        task['latest'] = s['messages'][-1][2] or task.get('latest', '')
    _post_questions(task, s)
    _post_milestones(task, s)
    if s['requests']:
        task['quiet_since'] = 0
        return
    if s['running'] or any(r for _, _, r in s['workers']):
        task['quiet_since'] = 0
        unpause(task)
        if quiet(task):
            return
        if not task.get('status_ts'):
            task.update(status_ts=slack.note_only(ch, tts, THINKING), line_start=time.time())
        line = working_line(task, s, now)
        if line != task['last_status'] and now - task['last_status_at'] >= STATUS_EVERY:
            slack.update(ch, task['status_ts'], 'thinking…', note=line)
            task.update(last_status=line, last_status_at=now)
        return
    if not task['quiet_since']:
        task['quiet_since'] = now
    if task['workers_said'] and now - task['quiet_since'] < SETTLE:  # orchestrators may start more workers
        return
    if s['last_status'] == 'interrupted' and now - task['quiet_since'] < 30:  # a new turn usually follows
        return
    if hold_for_limit(task, s, now) or retry_transient(task, s, now):
        return
    _finish_turn(task, s)


def how_to_answer(task, opts):
    dm = task['channel'].startswith('D')
    if opts:
        how = 'Reply with a number or in your own words.' if dm else 'Tag me with a number or your own words.'
    else:
        how = 'Reply in this thread.' if dm else 'Tag me in this thread to answer.'
    r = review_of(task)
    return how + (f' If other reviews here ask too, start with #{r["number"]}.' if r else '')


def _ask_by_message(task, final, items, foot):
    """The turn ended on a question answered by a plain message: post it with its numbered options, if any."""
    opts = {}
    for item in items:
        opts.update(question_text(item)[1])
    task['options'] = opts
    listed = '\n'.join(f'{n}️⃣ **{label}**' for n, label in opts.items())
    md = (final or 'The agent is waiting for your answer.') + (f'\n\n{listed}' if listed else '')
    reply(task, md, ' · '.join(x for x in (how_to_answer(task, opts), foot) if x), 'asked you')


def _post_questions(task, s):
    """Post the agent's new questions with numbered options."""
    for rid, kind, item in s['requests']:
        if rid in task['asked']:
            continue
        task['asked'].append(rid)
        if kind == 'user_input':
            body, opts = question_text(item)
            task['options'] = opts
            reply(task, body, how_to_answer(task, opts), 'asked you')
        else:
            reply(task, ':raised_hand: I need your approval for a step.', 'Approve it in the T3 app.', 'needs approval')


def _post_milestones(task, s):
    """Post new workers and pull requests as short lines."""
    ch, tts = task['channel'], task['thread_ts']
    if quiet(task):
        task['workers_said'] = len(s['workers'])
        return
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
    r = review_of(task)
    if r and not r.get('published') and s['last_status'] == 'completed' and task.get('nudged', 0) < 2:
        # a lead chat often ends its turn before publishing review.json
        task['nudged'] = task.get('nudged', 0) + 1
        res = t3.send(task['thread'], REVIEW_NUDGE)
        if res.get('ok'):
            task['quiet_since'] = 0
            log('review nudged to finish', r['id'])
            return
    ch = task['channel']
    task['retries'] = 0
    final = task.get('latest', '')
    took = parse_iso(s['last_done']) - parse_iso(task['burst_start']) if s['last_done'] else 0
    foot = ' · '.join(
        x for x in (AGENT, (task.get('project') or '').rsplit('/', 1)[-1], took >= 60 and mins(took)) if x
    )
    no_action = re.match(r'\s*`?NO_ACTION:?\s*(.*?)`?\s*$', final or '', re.S)
    status = s['last_status']
    posted = task.pop('posted', False)
    if posted and status == 'completed':
        if task.get('status_ts'):
            slack.update(ch, task['status_ts'], 'Posted', note=':seedling: Picked this up · posted ↓')
        task['status_ts'] = None
        outcome = 'posted'
    elif task.get('requester') and no_action:
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
        outcome = 'failed'
        if not quiet(task):  # a review's end is told by reviews.py, from `outcome`
            reply(task, ':x: **That failed.**\n\n' + final, foot, 'failed')
    elif status == 'cancelled':
        outcome = 'stopped'
        if not quiet(task):
            reply(task, ':black_square_for_stop: Stopped.', foot, 'stopped')
    elif s.get('asked'):
        _ask_by_message(task, final, s['asked'], foot)
        outcome = 'asked you'
    else:
        outcome = 'answered'
        if not quiet(task):
            reply(task, final or '_(no reply)_', foot)
    if task.get('reply_pending') and status == 'completed':
        errands.reply_requester(task, task.pop('reply_pending'), approved=True)
    slack.react(ch, task['trigger_ts'], 'eyes', remove=True)
    if review_of(task) and outcome != 'asked you':  # its result is posted; the chat only clutters T3 now
        jobs.run_later(t3.archive, task['thread'])
    COMP.event(
        'failed' if outcome == 'failed' else 'finished',
        f'{task.get("title", "")[:80]}: {outcome}',
        task=key_of(task),
        detail=first_sentence(no_emoji(final), 300),
        ok=outcome != 'failed',
    )
    task.update(active=False, quiet_since=0, last_status='', last_status_at=0, outcome=outcome, ended=now_iso())
