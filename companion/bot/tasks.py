"""Tasks: a Slack thread kept in sync with a T3 chat (start, follow_up, tick)."""

import re
import time
from typing import Literal

from . import cases, errands, jobs, ledger, limits, machine, polls, posts, projects, prompts, slack, t3
from .config import (
    AGENT,
    AGENT_DOWN_LIMIT,
    COMP,
    HISTORY_DAYS,
    NAME,
    OWNER,
    RESUME_GRACE,
    SETTLE,
    STATUS_EVERY,
    auto_retry,
    log,
    slack_for_github,
)
from .fsm import RETRY
from .shapes import Audit, Json, Line, Outcome, Place, Retry, Task, TurnBy
from .state import key, key_of, lock, new_task, now_iso, parse_iso, review_of, save, state
from .text import first_sentence, mins, no_emoji
from .when import say

THINKING = ':seedling: thinking…'


def post_line(ch: str, tts: str, note: str) -> Line | None:
    """A new thinking line: {ch, ts, since}, or None when Slack refused it. It is always edited where it was posted,
    whoever's turn it is now."""
    ts = slack.note_only(ch, tts, note)
    if not ts:
        return None
    return {'ch': ch, 'ts': ts, 'since': time.time()}


def set_line(task: Task, text: str, note: str) -> None:
    line = task['line']
    assert line, 'set_line needs a thinking line'
    slack.update(line['ch'], line['ts'], text, note=note)


def quiet(task: Task) -> bool:
    """A PR review: its progress shows on the batch card (reviews.py), so its thread gets only questions."""
    return bool(review_of(task))


def history_with(uid: str, now: float | None = None) -> list[str]:
    """What the companion did with this person in the last HISTORY_DAYS: their tasks, and reviews of pull requests
    they wrote or asked for (one line each, oldest first, at most 6)."""
    since = (now or time.time()) - HISTORY_DAYS * 86400
    rows = []
    for t in state['tasks'].values():
        at = parse_iso(t.get('start'))
        if at < since:
            continue
        r = review_of(t)
        outcome = 'in progress' if machine.running(t) else machine.outcome(t).replace('_', ' ') or 'ended'
        if r and (uid in (r.get('asked_by') or []) or slack_for_github(r.get('author')) == uid):
            what = f'Reviewed {r["id"]} ({r.get("title", "")[:60]}): {outcome}'
        elif not r and machine.party(t)['user'] == uid:
            what = f'Task "{t.get("title", "")[:80]}": {outcome}'
        else:
            continue
        rows.append((at, f'- [{say(at, "near")}] {no_emoji(what)[:300]} · T3 chat {t["thread"]}'))
    return [line for _, line in sorted(rows)[-6:]]


def start(
    channel: str,
    thread_ts: str,
    trigger_ts: str,
    text: str,
    elsewhere: tuple[str, list[Json]] | None = None,
    guest: str | None = None,
    approved: str | Literal[False] = False,
    via: str | None = None,
) -> None:
    """elsewhere: (where, messages) of a conversation the bot can't post in; guest: who asked, if not the owner;
    approved: the ts of the owner's approval card for the guest's ask (requests channel): the thread is mirrored
    under it, and follow-ups that leave the ask come back to the owner; via: how it came, for the audit."""
    k = key(channel, thread_ts)
    slack.react(channel, trigger_ts, 'eyes')
    folder = f'{channel}-{thread_ts.replace(".", "")}'
    msgs = elsewhere[1] if elsewhere else slack.thread_messages(channel, thread_ts, trigger_ts)
    lines, files = slack.transcript(msgs, folder)
    lead = [] if elsewhere else slack.lead_up(msgs, guest or OWNER, trigger_ts)
    parts = (slack.ask(t).strip() for t in [*(m.get('text') or '' for m in lead), text])
    ask = '\n'.join(p for p in parts if p) or 'Look at this thread and handle it.'
    if elsewhere:
        where = elsewhere[0]
    else:
        where = 'a DM with you' if channel.startswith('D') else f'Slack channel {channel}, thread {thread_ts}'
    chan = slack.channel_name(channel)
    where_to = projects.route('task', ask, '\n'.join(lines), chan)
    log('route', where_to)
    title = first_sentence(ask, 70).rstrip('.')
    here = '' if channel.startswith('D') else channel
    member = [c for c in slack.channels() if c['member']]
    open_polls = polls.for_prompt(channel, thread_ts)
    asker = slack.name(guest or OWNER)
    fresh = not elsewhere and thread_ts == trigger_ts
    history = history_with(guest or OWNER) if fresh else []
    prompt = prompts.task(
        ask,
        slack.name(OWNER),
        where,
        lines,
        files,
        folder,
        here,
        member,
        open_polls,
        guest and asker,
        fresh,
        bool(approved),
        history,
    )
    tid, err = t3.start_thread(where_to['project'], title, prompt)
    if not tid:
        slack.post(channel, thread_ts, f":warning: I couldn't start the chat in {AGENT}: {err}")
        slack.react(channel, trigger_ts, 'eyes', remove=True)
        COMP.event('failed', f'Could not start: {title}', task=k, detail=err, ok=False)
        return
    status = post_line(channel, thread_ts, THINKING)
    if elsewhere:
        via = via or f'in {elsewhere[0]}'
    how = audit(
        guest or OWNER,
        via or ('in a DM' if channel.startswith('D') else f'in #{chan}' if chan else 'in a channel'),
        OWNER if approved else None,
    )
    task = new_task(
        channel, thread_ts, tid, title, folder, trigger_ts, status, where_to, audit=how, party=machine.party_of(guest)
    )
    machine.begin_turn(task, 'colleague' if machine.is_colleague(task) else 'owner', 'thread')
    if machine.is_colleague(task):
        threaded = not elsewhere and thread_ts != trigger_ts
        before = [m for m in msgs if float(m['ts']) < float(trigger_ts) and m not in lead] if threaded else []
        cases.open_case(task, ask, f'in {elsewhere[0]}' if elsewhere else how['via'], approved or None, before)
    save()
    log('started', k, tid, 'for', guest or 'owner')
    COMP.event('started', title, task=k, detail=f'task from {asker} in ' + (f'#{chan}' if chan else 'a DM'))


def audit(by: str, via: str, approved_by: str | None = None, for_: str | None = None) -> Audit:
    """Who started a task and how, kept on it for the hub (started_by, via, approved_by)."""
    return {'by': by, 'via': via, 'approved_by': approved_by, 'for': for_, 'at': time.time()}


STATUS_ASK = re.compile(
    r"\b(status|progress|eta|update me|any updates?|an update|how(?:'s| is) it going|how far"
    r"|where (?:are|r) (?:we|you|u)|where(?:'s| is) it at|done yet|finished yet"
    r"|what(?:'s| are you| r u) (?:doing|working on|up|happening|going on)|what(?:'s| is) going on"
    r'|still (?:working|going|on it))\b',
    re.I,
)
INSTRUCTION = re.compile(
    r'^\W*(fix|add|change|update|remove|make|move|rename|check|look|use|set|try|run|open|create|delete|revert|test)\b',
    re.I,
)


POLL_WORDS = re.compile(r'\b(poll|vote|votes|voting)\b', re.I)


BTW = re.compile(r'^\s*/?btw\b[\s,:.-]*', re.I)


ONLY_UPDATE = re.compile(r'^\W*(?:any\s+)?(?:updates?|news)\W*$', re.I)  # "updates?" alone; not "push the updates"


def is_status_ask(msg: str) -> bool:
    """A short "how's it going?", not an instruction mentioning status ("fix the status badge")."""
    if ONLY_UPDATE.match(msg):
        return True
    return len(msg.split()) <= 8 and not INSTRUCTION.match(msg) and bool(STATUS_ASK.search(msg))


def is_side_question(msg: str) -> bool:
    """Answered on the side from the chat's record, never by the chat: a status ask, or anything starting with btw."""
    return is_status_ask(msg) or bool(BTW.match(msg) and BTW.sub('', msg).strip())


def side_reply(task: Task, question: str, ts: str, place: Place, lead: str = '') -> None:
    """Answer a side question with the quick model from the chat's record, without messaging the chat, at `place`
    (machine.PLACES): where it was asked. `lead`: a line before the answer. Falls back to the plain status summary
    (to just `lead`, when there is one)."""
    ch, tts = at(task, place)
    question = BTW.sub('', question).strip() or question
    res = t3.triage(prompts.side_answer(question, t3.digest(task['thread'])))
    text = str(res.get('result') or '').strip() if res.get('ok') else ''
    if not text and not lead:
        status_reply(task, ts, place)
        return
    text = f'{lead} Right now: {text}' if lead and text else lead or text
    slack.post(ch, tts, first_sentence(no_emoji(text), 150), md=text, note="Side answer · the agent wasn't interrupted")
    if task.get('case'):  # recorded for the case; it went where it was asked, not through the outbox
        to = 'colleague' if place == 'thread' and machine.is_colleague(task) else 'owner'
        ledger.add(
            task, 'message', 'sent', to=to, label=cases.who(task) if to == 'colleague' else '', text=text, side=True
        )
    task['seen_ts'] = ts  # keeps the question out of since_last
    save()


def where(task: Task) -> tuple[str, str]:
    """(channel, thread) the turn under way shows its progress in: where its message was written (machine.place)."""
    return at(task, machine.place(task))


def _case(task: Task) -> tuple[str, str]:
    c = cases.of(task)
    assert c, 'a case place needs a case'
    return c


def at(task: Task, place: Place) -> tuple[str, str]:
    """(channel, thread) of a place ('thread' | 'case', machine.PLACES)."""
    return _case(task) if place == 'case' else (task['channel'], task['thread_ts'])


def answer_place(task: Task) -> tuple[str, str]:
    """Where the turn's final message, and the agent's questions, go (machine.final_goes_to)."""
    return _case(task) if machine.final_goes_to(task) == 'case' else (task['channel'], task['thread_ts'])


def follow_up(
    task: Task,
    text: str,
    files: list[Json] | None,
    ts: str,
    place: Place,
    by: str | None = None,
    decision: bool = False,
) -> None:
    """A new message for the task's chat, written at `place` (machine.PLACES): it is answered there. by: who wrote it
    (None: the owner); decision: the owner's Approve / Reject passed on to the agent, not a message anyone typed.
    Side questions are answered on the side, where they were asked, and start no turn."""
    ch = task['channel']
    msg = slack.ask(text).strip()
    m = re.fullmatch(r'\s*([1-9])\s*[.)]?\s*', msg)
    picked = m is not None and m.group(1) in task.get('options', {})
    if picked and m:  # "1" picks option 1 of the last question
        msg = task['options'][m.group(1)]
    by = by or OWNER
    other = by != OWNER
    if other and not task.get('case') and machine.party(task)['kind'] == 'owner':
        how = task.get('audit')
        started_by = how.get('by') if how else None
        if started_by and started_by != OWNER:  # e.g. a review a colleague asked for: they talk to the companion now
            cases.open_late(task, by, text)
    if task.get('case') and place == 'thread' and not decision:  # everyone's words in the thread, the owner's too
        cases.heard(task, by, text, files or (), ts=ts)
    if is_side_question(msg) and not files and not decision and not picked:
        side_reply(task, msg, ts, place)
        return
    colleague = other and machine.is_colleague(task) and by == machine.party(task)['user']
    if colleague and machine.owners_turn(task):  # the owner is talking to the agent: theirs comes next
        cases.queue(task, {'by': by, 'text': text, 'files': files, 'ts': ts})
        return
    if machine.party(task)['kind'] != 'owner' or other:
        msg = f'{slack.name(by)}: {msg}'
    case = task.get('case')
    if colleague and case and case.get('head') == 'card':  # an ask the owner approved: stay within it
        msg += prompts.follow_up_reminder(slack.name(OWNER))
    if colleague and machine.case_mode(task) == 'private':
        msg += prompts.colleague_turn(slack.name(by), slack.name(OWNER))
    if not other and not decision and place == 'thread' and machine.case_mode(task) == 'private':
        msg += prompts.owner_in_thread(slack.name(OWNER), cases.who(task))
    folder = f'{ch}-{task["thread_ts"].replace(".", "")}'
    paths = slack.download(files, folder)
    between, more = ([], []) if quiet(task) else since_last(task, ts, folder)  # a batch thread mixes reviews
    if between:
        msg = 'Meanwhile in the Slack thread:\n' + '\n'.join(between) + '\n\nMy message now:\n' + msg
        paths += more
    if paths:
        msg += '\n\nFiles (saved for you):\n' + '\n'.join(f'- {p}' for p in paths)
    sent = posts.sent_list(task)
    if sent:
        msg += '\n\n---' + prompts.editing(slack.name(OWNER), sent)
    open_polls = polls.for_prompt(ch, task['thread_ts'])
    if open_polls and POLL_WORDS.search(msg):
        msg += '\n\n---' + prompts.poll_changes(slack.name(OWNER), open_polls)
    slack.react(ch, ts, 'eyes')
    res: t3.Reply = {}
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
    queued = (res.get('result') or {}).get('delivery') == 'queued'  # T3 can't steer for us: say so
    if queued and decision:
        slack.note_only(*errands.approver(task), ':inbox_tray: The agent gets your decision when its current step ends')
    elif queued:
        lead = ':inbox_tray: Queued: the agent reads this when its current step ends.'
        jobs.run_later(side_reply, task, 'What is it doing right now?', ts, place, lead)
    turn_by: TurnBy = 'decision' if decision else 'colleague' if other else 'owner'
    turn_place = 'thread' if decision else place  # a decision is answered where the work is (or privately: machine)
    now = now_iso()
    with lock:
        machine.set_asking(task, False)  # this message answers any question it asked
        if machine.running(task):
            machine.retake_turn(task, turn_by, turn_place)
        else:
            machine.begin_turn(task, turn_by, turn_place)
            task.update({'burst_start': now, 'step_from': now, 'line': None, 'ended': ''})
        task.update(
            {'trigger_ts': ts, 'seen_ts': ts, 'quiet_since': 0, 'options': {}, 'last_status': '', 'last_status_at': 0}
        )
        line = task.get('line')
        if line and line['ch'] != where(task)[0]:  # the turn moved: its progress follows it
            set_line(
                task, 'Continued where the newer message was written', ':seedling: continued below a newer message'
            )
            task['line'] = None
        if not task.get('line') and not quiet(task):
            task['line'] = post_line(*where(task), THINKING)
    save()


def since_last(task: Task, ts: str, folder: str) -> tuple[list[str], list[str]]:
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


def status_reply(task: Task, ts: str, place: Place) -> None:
    """Answer "status?" from T3's record without messaging the busy chat, at `place`: where it was asked."""
    tid = task['thread']
    s = t3.snapshot(tid, task.get('burst_start') or '')
    run = t3.open_run_since(tid)
    since = f' for {mins(time.time() - parse_iso(run))}' if run else ''
    out = [f':hourglass_flowing_sand: **Still working{since}.**']
    last = t3.last_answer(tid)
    if last:
        out.append(f'Latest: {first_sentence(last, 300)}')
    running = [t or 'a worker' for _, t, r in s['workers'] if r]
    done = [t for _, t, r in s['workers'] if not r]
    if running:
        out.append(f':jigsaw: Workers running: {", ".join(running[:6])}' + (f' ({len(done)} finished)' if done else ''))
    out += [f':link: <{pr["url"]}|PR #{pr.get("number", "")}>' for pr in s['prs'] if pr.get('url')]
    if s['requests']:
        out.append(":question: It's waiting on your answer to a question above.")
    slack.post(
        *at(task, place),
        f'Still working{since}',
        md='\n\n'.join(out),
        note="Status from T3 · the agent wasn't interrupted",
    )
    task['seen_ts'] = ts  # keeps the "status?" out of since_last
    save()


def question_text(item: Json) -> tuple[str, dict[str, str]]:
    out: list[str] = []
    opts: dict[str, str] = {}
    n = 0
    for qq in item.get('questions') or []:
        head = qq.get('header') if qq.get('header') not in (None, '', 'Question') else ''
        out.append(f'**{head}:** {qq.get("question", "")}' if head else qq.get('question', ''))
        for o in qq.get('options') or []:
            n += 1
            label, desc = o.get('label', ''), o.get('description', '')
            opts[str(n)] = label
            out.append(f'{n}️⃣ **{label}**' + (f' — {desc}' if desc and desc != label else ''))
    return '\n\n'.join(out) or 'The agent is waiting for your answer.', opts


def working_line(task: Task, s: t3.Snapshot, now: float) -> str:
    """Text of the live 'thinking' line."""
    elapsed = now - parse_iso(task['burst_start'])
    running = sum(1 for _, _, r in s['workers'] if r)
    bits = [mins(elapsed)] if elapsed >= 60 else []
    if running:
        bits.append(f'{running} worker{"s" if running > 1 else ""} running')
    step = first_sentence(task.get('latest', '')) if task.get('step_from', '') < task['seen'] else ''
    return f':seedling: {step or "thinking…"}' + (f'  ·  {" · ".join(bits)}' if bits else '')


def _close_line(task: Task, end: str) -> None:
    """Close the thinking line where the turn showed its progress."""
    shown = task.get('line')
    if shown:
        elapsed = time.time() - shown['since']
        n = task.get('workers_said', 0)
        bits = [
            'Picked this up',
            f'worked {mins(elapsed)}' if elapsed >= 60 else '',
            f'{n} worker{"s" if n > 1 else ""}' if n else '',
            end,
        ]
        line = ':seedling: ' + ' · '.join(b for b in bits if b)
        set_line(task, no_emoji(line), line)
    task['line'] = None


def _sent_to_colleague(task: Task) -> bool:
    return any(
        i['kind'] == 'message' and i.get('to') == 'colleague' and i['state'] == 'sent' and not i.get('side')
        for i in ledger.turn_items(task)
    )


def reply(task: Task, md: str, note: str | None = None, outcome: str = 'answered below') -> None:
    """The agent's final message (or question) of the turn, where machine.final_goes_to says, as a new message (Slack
    notifies on new messages, not edits), recorded in the ledger."""
    dest = machine.final_goes_to(task)
    if dest == 'case' and not machine.owners_turn(task):  # a colleague's turn: they have what the agent sent them
        told = _sent_to_colleague(task)
        _close_line(
            task, 'replied ↓' if told else {'failed': "that didn't work", 'stopped': 'stopped'}.get(outcome, 'done')
        )
        if not told and outcome == 'failed':
            slack.post(
                task['channel'],
                task['thread_ts'],
                "That didn't work",
                md=f":x: That didn't work. {slack.name(OWNER)} has the details.",
            )
        nothing = (
            ''
            if told
            else f'\n_Nothing was sent to {cases.who(task)} this turn. Reply here to tell {NAME} what to send._'
        )
        cases.note(task, f'**{NAME} → you:**\n{_clip(md, 2900)}{nothing}', f'{NAME} to you about {cases.who(task)}')
    else:
        r = review_of(task)
        if r:  # reviews of a batch share its thread
            md = f':mag: **<{r["url"]}|{r["id"]}>**\n{md}'
        _close_line(task, f'{outcome} ↓')
        slack.post(*answer_place(task), first_sentence(no_emoji(md), 300) or 'Reply', md=md, note=note)
    ledger.add(
        task,
        'final',
        'sent',
        to=dest,
        label='you' if dest == 'case' else '',
        text=_clip(md, 2900),
        question=outcome in ('asked you', 'needs approval'),
    )


def _clip(md: str, limit: int) -> str:
    return md if len(md) <= limit else md[:limit].rsplit('\n', 1)[0] + '\n…'


TRANSIENT = re.compile(
    r'at capacity|rate.?limit|too many requests|overloaded|temporarily unavailable|try again later'
    r'|\b(429|500|502|503|504|529)\b|timed? ?out|connection (reset|closed|error)',
    re.I,
)
RETRY_WAITS = (30, 90, 180)  # seconds before each automatic "continue"


RETRY_GRACE = 45  # seconds a sent "continue" gets to start a run


def retry_of(task: Task) -> Retry:
    """The task's retry record (fsm.RETRY)."""
    if 'retry' not in task:
        reset_retry(task)
    return task['retry']


def reset_retry(task: Task) -> None:
    """No retry pending and none used: a new turn, or a usage-limit pause (which is not retried)."""
    task['retry'] = {'state': RETRY.first('idle'), 'count': 0, 'at': 0}


def retry_transient(task: Task, s: t3.Snapshot, now: float) -> bool:
    """Send "continue" after a transient failure, up to 3 times; True while a retry is pending."""
    r = retry_of(task)
    if RETRY.is_(r.get('state'), 'sent'):
        if now - r['at'] < RETRY_GRACE:
            return True
        r['state'] = RETRY.to(r.get('state'), 'idle')
    if RETRY.is_(r.get('state'), 'waiting'):
        if now < r['at']:
            return True
        if not t3.send(task['thread'], 'continue').get('ok'):
            r['state'] = RETRY.to(r.get('state'), 'idle')
            return False
        r['state'] = RETRY.to(r.get('state'), 'sent')
        r['at'] = now
        log('retry sent', task['thread'], r['count'])
        COMP.event(
            'retry',
            f'Model busy, said "continue" ({r["count"]}/{len(RETRY_WAITS)})',
            task=key_of(task),
            detail=task.get('title', ''),
        )
        return True
    if (
        not auto_retry()
        or s['last_status'] != 'failed'
        or r['count'] >= len(RETRY_WAITS)
        or not TRANSIENT.search(t3.run_error(task['thread']))
    ):
        return False
    r['count'] += 1
    n = r['count']
    wait = RETRY_WAITS[n - 1]
    r['state'] = RETRY.to(r.get('state'), 'waiting')
    r['at'] = now + wait
    line = f':hourglass_flowing_sand: The model is busy, so I\'ll say "continue" in {wait} s ({n}/{len(RETRY_WAITS)})'
    if task.get('line'):
        set_line(task, 'Retrying soon', line)
    elif not quiet(task):
        task['line'] = post_line(*where(task), line)
    return True


LIMIT_GRACE = 15 * 60  # after the reset, T3's own resume gets this long before Leafy says "continue"
LIMIT_UNKNOWN = 5 * 3600  # no reset time given: the 5-hour window at most
LIMIT_NOTICE = 200  # longer answers are real work that mentions limits, not the notice itself


def _notice(task: Task, now: float | None = None) -> tuple[bool, float | None]:
    """The chat's last answer, when all it says is the limit notice ("You've hit your 5-hour limit · resets …")."""
    latest = task.get('latest') or ''
    return limits.parse(latest, now) if len(latest) <= LIMIT_NOTICE else (False, None)


def limit_hit(task: Task, s: t3.Snapshot) -> tuple[bool, float | None]:
    """(True, reset epoch or None) when the chat's last run stopped on a usage limit."""
    if s['last_status'] == 'failed':
        hit, at = limits.from_error(t3.run_error(task['thread']))
        return (hit, at) if hit else _notice(task)
    return _notice(task) if s['last_status'] == 'completed' else (False, None)


def paused_line(resumes_at: float | None) -> str:
    when = f'at {say(resumes_at, "near")}' if resumes_at else 'when it resets'
    return f':double_vertical_bar: Paused for the usage limit · T3 picks it up again {when}'


def pause(task: Task, resumes_at: float | None, run: str | None, now: float) -> None:
    """Wait for T3 to resume the chat at the reset: no retries, no failure."""
    first = not machine.paused(task)
    reset_retry(task)
    machine.pause(task, now, resumes_at, run)
    line = paused_line(resumes_at)
    if task.get('line') and not quiet(task):
        set_line(task, 'Paused for the usage limit', line)
    elif not quiet(task):
        task['line'] = post_line(*where(task), line)
    if first:
        log('paused for the usage limit', task['thread'], resumes_at)
        COMP.event(
            'paused',
            f'Paused for the usage limit: {task.get("title", "")[:80]}',
            task=key_of(task),
            detail=f'resumes at {say(resumes_at, "near")}' if resumes_at else 'resumes when the limit resets',
        )


def unpause(task: Task) -> None:
    if machine.paused(task):
        task.update({'last_status': '', 'last_status_at': 0})
        machine.unpause(task)
        log('resumed after the usage limit', task['thread'])


def hold_for_limit(task: Task, s: t3.Snapshot, now: float) -> bool:
    """True while a usage-limited chat waits for T3 to resume it (or once that wait has been closed)."""
    p = machine.paused(task)
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
        machine.unpause(task)  # T3 never resumed it: the turn ends as it stands
        _finish_turn(task, s)
        return True
    hit, resumes_at = limit_hit(task, s)
    if not hit:
        unpause(task)
        return False
    pause(task, resumes_at, s['last_done'], now)
    return True


def resume_if_running(task: Task) -> bool:
    """Reactivate a finished task (under 3 days old) whose chat is running again."""
    if time.time() - parse_iso(task.get('start')) > 3 * 86400 or not t3.has_open_run(task['thread']):
        return False
    now = now_iso()
    machine.begin_turn(task, 't3', 'case' if task.get('case') else 'thread')  # the owner, in T3: privately
    task.update(
        {
            'burst_start': now,
            'step_from': now,
            'quiet_since': 0,
            'last_status': '',
            'last_status_at': 0,
            'line': None,
            'ended': '',
        }
    )
    log('following a turn started outside Slack', task['thread'])
    return True


def tick(task: Task) -> None:
    if not machine.running(task) and not resume_if_running(task):
        return
    ch, tts = where(task)
    s = t3.snapshot(task['thread'], task['seen'])
    now = time.time()
    machine.set_asking(task, bool(s['requests'] or s.get('asked')))
    if s['messages']:
        task['seen'] = s['messages'][-1][1] or task['seen']
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
        if not task.get('line'):
            task['line'] = post_line(ch, tts, THINKING)
        line = working_line(task, s, now)
        if line != task['last_status'] and now - task['last_status_at'] >= STATUS_EVERY:
            set_line(task, 'thinking…', line)
            task.update({'last_status': line, 'last_status_at': now})
        return
    if not task['quiet_since']:
        task['quiet_since'] = now
    if task['workers_said'] and now - task['quiet_since'] < SETTLE:  # orchestrators may start more workers
        return
    if restarting(task, s, now):
        return
    if hold_for_limit(task, s, now) or retry_transient(task, s, now):
        return
    _finish_turn(task, s)


def how_to_answer(task: Task, opts: dict[str, str]) -> str:
    dm = task['channel'].startswith('D')
    if opts:
        how = 'Reply with a number or in your own words.' if dm else 'Tag me with a number or your own words.'
    else:
        how = 'Reply in this thread.' if dm else 'Tag me in this thread to answer.'
    r = review_of(task)
    return how + (f' If other reviews here ask too, start with #{r["number"]}.' if r else '')


def _ask_by_message(task: Task, final: str, items: list[Json], foot: str) -> None:
    """The turn ended on a question answered by a plain message: post it with its numbered options, if any."""
    opts: dict[str, str] = {}
    for item in items:
        opts.update(question_text(item)[1])
    task['options'] = opts
    listed = '\n'.join(f'{n}️⃣ **{label}**' for n, label in opts.items())
    md = (final or 'The agent is waiting for your answer.') + (f'\n\n{listed}' if listed else '')
    reply(task, md, ' · '.join(x for x in (how_to_answer(task, opts), foot) if x), 'asked you')


def _post_questions(task: Task, s: t3.Snapshot) -> None:
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


def _post_milestones(task: Task, s: t3.Snapshot) -> None:
    """Post new workers and pull requests as short lines."""
    ch, tts = where(task)
    if quiet(task):
        task['workers_said'] = len(s['workers'])
        return
    if len(s['workers']) > task['workers_said']:
        new = [t or 'a worker' for _, t, _ in s['workers']][task['workers_said'] :]
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
    'Every helper you started has reported back. Collect what they found, run the verification step, write qa.md (when QA'
    ' ran) and review.json exactly as your brief says, settle this chat (t3_thread_organize, action "settle"), then'
    ' end with the one-line summary.'
)


def restarting(task: Task, s: t3.Snapshot, now: float) -> bool:
    """The agent is restarting or T3 has yet to resume what a restart cut off: nothing is over yet."""
    if not t3.agent_up():
        task.setdefault('down_since', now)
        if now - task['down_since'] < AGENT_DOWN_LIMIT:
            return True
    else:
        task.pop('down_since', None)
    cut = s.get('interrupted_at')
    return bool(cut) and now - parse_iso(cut) < RESUME_GRACE


NO_ACTION = re.compile(r'\s*`?NO_ACTION:?\s*(.*?)`?\s*$', re.S)  # an errand that needs nothing from the companion
NO_REPLY = re.compile(r'\s*`?NO_REPLY:?\s*(.*?)`?\s*$', re.S)  # nothing new to say this turn


def _finish_turn(task: Task, s: t3.Snapshot) -> None:
    """The turn is over: its final message goes out (reply), the turn ends with an explicit outcome, and whatever
    waited for it goes next."""
    r = review_of(task)
    if r and not r.get('published') and s['last_status'] == 'completed' and task.get('nudged', 0) < 2:
        # a lead chat often ends its turn before publishing review.json
        task['nudged'] = task.get('nudged', 0) + 1
        res = t3.send(task['thread'], REVIEW_NUDGE)
        if res.get('ok'):
            task['quiet_since'] = 0
            log('review nudged to finish', r['id'])
            return
    reset_retry(task)
    final = task.get('latest', '')
    took = parse_iso(s['last_done']) - parse_iso(task['burst_start']) if s['last_done'] else 0
    took_line = mins(took) if took >= 60 else ''
    foot = ' · '.join(x for x in (AGENT, task['route']['project'].rsplit('/', 1)[-1], took_line) if x)
    status = s['last_status']
    no_action = NO_ACTION.match(final or '') if machine.party(task)['kind'] == 'errand' else None
    no_reply = NO_REPLY.match(final or '')
    outcome: Outcome
    if status == 'failed':
        outcome = 'failed'
        if not quiet(task):  # a review's end is told by reviews.py, from the outcome
            reply(task, ':x: **That failed.**\n\n' + final, foot, 'failed')
    elif status == 'cancelled':
        outcome = 'stopped'
        if not quiet(task):
            reply(task, ':black_square_for_stop: Stopped.', foot, 'stopped')
    elif no_action:
        outcome = 'nothing_to_do'
        final = no_action.group(1).strip()[:200] or 'Nothing for me to do.'
        _close_line(task, f'nothing for me to do: {final}')
        errands.close_head(task, ':white_check_mark: Nothing needed', 'white_check_mark')
        ledger.add(task, 'final', 'silent', to=machine.final_goes_to(task), text=final)
    elif no_reply:
        outcome = 'silent'
        final = no_reply.group(1).strip() or 'Nothing new to say.'
        _close_line(task, 'done')
        ledger.add(task, 'final', 'silent', to=machine.final_goes_to(task), text=final)
    elif s.get('asked'):
        outcome = 'asked'
        _ask_by_message(task, final, s['asked'], foot)
    else:
        outcome = 'answered'
        if not quiet(task):
            reply(task, final or '_(no reply)_', foot)
    errands.after_turn(task, completed=status == 'completed')
    slack.react(task['channel'], task['trigger_ts'], 'eyes', remove=True)
    COMP.event(
        'failed' if outcome == 'failed' else 'finished',
        f'{task.get("title", "")[:80]}: {outcome.replace("_", " ")}',
        task=key_of(task),
        detail=first_sentence(no_emoji(final), 300),
        ok=outcome != 'failed',
    )
    task.update({'quiet_since': 0, 'last_status': '', 'last_status_at': 0, 'ended': now_iso()})
    machine.end_turn(task, outcome)
    waiting = cases.next_in_line(task)
    if waiting and waiting['by'] == OWNER:
        jobs.run_later(cases.ask, task, waiting['text'], waiting['files'], waiting['ts'])
    elif waiting:
        jobs.run_later(follow_up, task, waiting['text'], waiting['files'], waiting['ts'], 'thread', waiting['by'])
