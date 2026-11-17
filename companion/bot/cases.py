"""Cases: every conversation a colleague has with the companion, followed by the owner from one thread in their DM.

The colleague's thread is theirs and the companion's; the case thread is the owner's and the companion's, with a copy of
everything said to and by the colleague. Whoever starts a turn gets its answer: the colleague's turns are answered in
their thread (copied to the case), the owner's (in the case thread, or in T3 directly) only in the case thread. The
companion sends the colleague something on the owner's word with send.json, and the case shows exactly what went."""

import os
import time
from datetime import datetime

from . import prompts, slack, t3
from .config import COMP, NAME, OWNER, log
from .state import key_of, lock, now_iso, save, state
from .text import first_sentence, no_emoji, quote

THINKING = ':seedling: thinking…'


def of(task):
    """(channel, ts) of the task's case head, or None for the owner's own tasks. A requests-channel ask from before
    cases has its card instead."""
    c = task.get('case')
    if c:
        return c['ch'], c['ts']
    card = task.get('approved')
    return (slack.dm_owner(), card) if isinstance(card, str) and card else None


def who(task):
    return slack.name(task.get('guest') or task.get('requester') or OWNER)


def open_case(task, ask, where, card=None):
    """Open the owner's case for a colleague's new task; `card`: the requests channel's card, which serves as its head."""
    dm = slack.dm_owner()
    COMP.event('received', f'{who(task)} wrote', task=key_of(task), detail=slack.ask(ask).strip())
    if card:
        task['case'] = {'ch': dm, 'ts': card, 'own': False}
        return
    link = slack.permalink(task['channel'], task['thread_ts'])
    md = (
        f':speech_balloon: **{who(task)}** messaged {NAME} {where}'
        + (f' · <{link}|open>' if link else '')
        + '\n'
        + quote(first_sentence(ask, 600))
    )
    ts = slack.post(
        dm, None, f'{who(task)} messaged {NAME}: {first_sentence(ask, 120)}', md=md, note=_note('working', who(task))
    )
    if ts:
        task['case'] = {'ch': dm, 'ts': ts, 'own': True, 'md': md}


def _note(state_, name):
    t = datetime.now().strftime('%H:%M')
    return {
        'working': f':seedling: {NAME} is working on it · reply here to talk to {NAME}; {name} sees nothing of it',
        'answered': f':white_check_mark: Answered at {t} · reply here to talk to {NAME} about it',
        'waiting': f':hourglass_flowing_sand: Waiting for your approval below (since {t})',
        'stopped': f':black_square_for_stop: Stopped at {t}',
        'failed': f':x: Failed at {t} · reply here to talk to {NAME} about it',
    }[state_]


def status(task, state_):
    """The head's grey line: working / answered / waiting / stopped / failed."""
    c = task.get('case')
    if not c or not c.get('own'):
        return
    slack.update(c['ch'], c['ts'], 'case', md=c['md'], note=_note(state_, who(task)))


def note(task, md, text=None):
    """Post `md` into the case thread."""
    at = of(task)
    if at:
        slack.post(*at, text or first_sentence(no_emoji(md), 150) or 'Update', md=md)


def at(ch, thread_ts):
    """The task whose case head (or an approval card from before cases) is `thread_ts` in `ch`."""
    for task in state['tasks'].values():
        c, a = task.get('case') or {}, task.get('approval') or {}
        if (c.get('ts') == thread_ts and c.get('ch') == ch) or (a.get('ts') == thread_ts and a.get('ch') == ch):
            return task
    return None


def owners_turn(task):
    return bool(task.get('answer_to'))


def make_private(task):
    """The turn under way is the owner's: its answer and its status lines go to the case thread."""
    c = of(task)
    if c:
        task['answer_to'] = {'ch': c[0], 'tts': c[1]}


def colleague_said(task, text, files=()):
    """Copy a colleague's message into the case."""
    said = slack.ask(text).strip() or '(files)'
    note(task, f'**{who(task)}:**\n' + quote(said) + (f'\n_{len(files)} file(s)_' if files else ''))
    COMP.event('received', f'{who(task)} wrote', task=key_of(task), detail=said)


def answered_owner(task, md):
    """The agent's answer to the owner's private turn (already posted in the case thread): kept for the hub."""
    COMP.event('private', f'{NAME} answered you', task=key_of(task), detail=md)


def answered(task, md):
    """Leafy's answer to the colleague, sent in their thread: copied to the case, listed in the hub."""
    note(task, f'**{NAME} → {who(task)}:**\n{md}', f'{NAME} replied to {who(task)}')
    COMP.event('sent', f'Reply to {who(task)}', task=key_of(task), to=who(task), detail=md)


def ask(task, text, files, ts, msg_for_agent=None):
    """The owner talks to the companion about a case: privately, answered in the case thread only."""
    c = of(task)
    if not c:
        return
    if task.get('active'):
        queue(task, {'by': OWNER, 'text': text, 'files': files, 'ts': ts})
        slack.post(
            *c, 'Queued', md=f':hourglass_flowing_sand: {NAME} is still answering {who(task)}; it reads this next.'
        )
        return
    a = task.get('approval') or {}
    pending = a.get('action') if a and not a.get('decided') else ''
    msg = msg_for_agent or prompts.owner_private(
        slack.name(OWNER), who(task), prompts.outbox(task['outbox']), slack.ask(text).strip(), pending
    )
    paths = slack.download(files, f'{task["channel"]}-{task["thread_ts"].replace(".", "")}')
    if paths:
        msg += '\n\nFiles (saved for you):\n' + '\n'.join(f'- {p}' for p in paths)
    res = t3.send(task['thread'], msg)
    if not res.get('ok'):
        slack.post(*c, 'Could not ask', md=f":warning: I couldn't pass that on: {t3.error_text(res)}")
        return
    slack.react(c[0], ts, 'eyes')
    COMP.event('private', f'You asked {NAME}', task=key_of(task), detail=slack.ask(text).strip())
    with lock:
        now = now_iso()
        make_private(task)
        task.update(
            active=True,
            burst_start=now,
            step_from=now,
            ended='',
            trigger_ts=ts,
            seen_ts=ts,
            quiet_since=0,
            options={},
            question=False,
            last_status='',
            last_status_at=0,
            status_ts=slack.note_only(*c, THINKING),
            line_start=time.time(),
        )
    status(task, 'working')
    save()


def queue(task, item):
    task.setdefault('queue', []).append(item)
    save()


def next_in_line(task):
    """After a turn: the oldest message that waited for it, or None."""
    q = task.get('queue') or []
    return q.pop(0) if q else None


def send(task, s, ok=(), refused=()):
    """send.json: a message to the colleague on the owner's word, in their thread at once; the case shows it.
    ok / refused: its files, already through the outbox's gate."""
    text = str(s.get('text') or '').strip()[:3000]
    name = who(task)
    if not of(task) or not text:
        log('send.json ignored: no case or no text', task.get('thread'))
        return
    if not slack.post(task['channel'], task['thread_ts'], first_sentence(no_emoji(text), 200) or 'Message', md=text):
        note(task, f":warning: Couldn't send that to **{name}**. Nothing went out.")
        return
    if ok:
        slack.upload(task['channel'], task['thread_ts'], ok)
    files = f'\n_With {len(ok)} file(s): {", ".join(os.path.basename(p) for p in ok)}_' if ok else ''
    held = f'\n:no_entry: Held back: {", ".join(refused)}' if refused else ''
    note(task, f':outbox_tray: **Sent to {name}:**\n{text}{files}{held}', f'Sent to {name}')
    COMP.event('sent', f'Message to {name} (on your word)', task=key_of(task), to=name, detail=text)
    save()
