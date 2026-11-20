"""Cases: every conversation someone other than the owner has with the companion, followed by the owner from one
thread in their DM (machine.py names the case's head and mode; ledger.py holds what was said).

The colleague's thread is theirs and the companion's; the case thread is the owner's and the companion's. Every message
in and out is a ledger item, and this module renders the items into the case thread: what the colleague wrote, what the
agent sent them, and anything refused or failed. A colleague's turn ends with the owner (machine final_goes_to). The
owner's own messages in the case thread (or in T3 directly) are private turns; what the owner writes in the
colleague's thread is public and answered there (machine turn place)."""

import os
import time
from collections.abc import Iterable, Sequence

from . import ledger, machine, prompts, slack, t3
from .config import COMP, NAME, OWNER, log
from .shapes import Item, ItemFields, Json, Queued, Task
from .state import key_of, lock, now_iso, save, state
from .text import first_sentence, no_emoji, quote
from .when import say

THINKING = ':seedling: thinking…'


def of(task: Task) -> tuple[str, str] | None:
    """(channel, ts) of the task's case thread, or None (the owner's own task)."""
    c = task.get('case')
    return (c['ch'], c['ts']) if c else None


def owner_place(task: Task) -> tuple[str, str]:
    """Where the owner reads about this task: its case thread, else its own thread."""
    return of(task) or (task['channel'], task['thread_ts'])


def who(task: Task) -> str:
    return slack.name(machine.party(task)['user'])


def _head_md(task: Task, ask: str, where: str) -> str:
    link = slack.permalink(task['channel'], task['thread_ts'])
    return (
        f':speech_balloon: **{who(task)}** messaged {NAME} {where}'
        + (f' · <{link}|open>' if link else '')
        + '\n'
        + quote(first_sentence(ask, 600))
    )


def open_case(task: Task, ask: str, where: str, card: str | None = None, earlier: Iterable[Json] = ()) -> None:
    """The owner's case for a colleague's new task: a head message in their DM, or the requests channel's card.
    earlier: the thread's messages before the ask, synced into the case too."""
    dm = slack.dm_owner()
    if card:
        machine.open_case(task, dm, card, 'card')
    else:
        md = _head_md(task, ask, where)
        ts = slack.post(dm, None, f'{who(task)} messaged {NAME}: {first_sentence(ask, 120)}', md=md)
        if not ts:
            log('case head not posted', key_of(task))
            return
        machine.open_case(task, dm, ts, 'own', md=md)
    _earlier(task, earlier)
    heard(task, machine.party(task)['user'], ask, first=True, ts=task['trigger_ts'])
    status(task)
    save()


def _earlier(task: Task, msgs: Iterable[Json]) -> None:
    """The thread before the case opened, into the case: it is synced whole, not from the tag on."""
    me = slack.bot_user()
    said: list[str] = []
    with ledger.muted():
        for m in msgs:
            if m.get('user') in (None, me) or m.get('bot_id') or m['ts'] == task['trigger_ts']:
                continue
            it = heard(task, m['user'], m.get('text') or '', m.get('files') or (), ts=m['ts'])
            if it:
                said.append(f'**{it["label"]}:**\n' + quote(it['text']))
    if said:
        note(task, '**Earlier in the thread:**\n' + '\n'.join(said), 'Earlier in the thread')


def in_thread(task: Task, ev: Json) -> None:
    """Anyone's message in a case's thread, tagged or not: the case follows the whole thread."""
    if task.get('case') and ev.get('user') and ev.get('user') != slack.bot_user():
        heard(task, ev['user'], ev.get('text') or '', ev.get('files') or (), ts=ev['ts'])
        save()


def open_late(task: Task, by: str, text: str) -> None:
    """A colleague talks in a task started without a case (a review they asked for): a shared case, from now on."""
    chan = slack.channel_name(task['channel'])
    machine.set_party(task, 'colleague', by)
    dm = slack.dm_owner()
    md = _head_md(task, text, f'in #{chan}' if chan else 'in a DM')
    ts = slack.post(dm, None, f'{who(task)} wrote to {NAME}: {first_sentence(text, 120)}', md=md)
    if ts:
        machine.open_case(task, dm, ts, 'own', mode='shared', md=md)
        status(task)
    save()


_NOTES = {
    'working': ':seedling: {me} is working on it · reply here to talk to {me}; {name} sees nothing of it',
    'waiting_owner': ':hourglass_flowing_sand: Waiting for you: {n} below',
    'waiting_answer': ':grey_question: {me} asked a question',
    'paused': ':double_vertical_bar: Paused for the usage limit',
    'answered': ':white_check_mark: Answered at {t} · reply here to talk to {me} about it',
    'nothing_to_do': ':white_check_mark: Nothing to do · {t}',
    'stopped': ':black_square_for_stop: Stopped at {t}',
    'failed': ':x: Failed at {t} · reply here to talk to {me} about it',
}


def status(task: Task) -> None:
    """The head's grey line, from the task's phase."""
    c = task.get('case')
    if not c or c.get('head') != 'own':
        return
    n = len(ledger.pending(task))
    line = _NOTES[task.get('phase') or 'working'].format(
        me=NAME, name=who(task), t=say(), n=f'{n} item{"s" if n != 1 else ""}'
    )
    slack.update(c['ch'], c['ts'], 'case', md=c.get('md'), note=line)


machine.on_phase(status)


def note(task: Task, md: str, text: str | None = None) -> None:
    """Post `md` where the owner follows the task."""
    slack.post(*owner_place(task), text or first_sentence(no_emoji(md), 150) or 'Update', md=md)


def at(ch: str, thread_ts: str) -> Task | None:
    """The task whose case head, or a card waiting on the owner, is `thread_ts` in `ch`."""
    for task in state['tasks'].values():
        c = task.get('case')
        if c and c.get('ts') == thread_ts and c.get('ch') == ch and c.get('head') != 'errand':
            return task
        it = ledger.on_card(task, thread_ts)
        if it and 'card' in it and it['card']['ch'] == ch and task.get('case'):
            return task
    return None


def heard(
    task: Task,
    by: str,
    text: str,
    files: Iterable[Json | str] | None = (),
    private: bool = False,
    first: bool = False,
    ts: str | None = None,
) -> Item | None:
    """A message in the task's thread or to the companion, into the ledger (and so into the case). ts: its Slack ts,
    so each message is recorded once however it arrives (live, tagged, or with the thread so far)."""
    if ts and any(i['kind'] == 'in' and i.get('ts') == ts for i in ledger.items(task)):
        return None
    said = slack.ask(text).strip() or ('(files)' if files else f'(tagged {NAME})')
    fields: ItemFields = {
        'by': by,
        'label': slack.name(by),
        'text': said,
        'files': [os.path.basename(str(f.get('name') if isinstance(f, dict) else f)) for f in files or ()],
    }
    if private:  # ledger.add drops fields given as None
        fields['private'] = True
    if first:
        fields['first'] = True
    if ts is not None:
        fields['ts'] = ts
    it = ledger.add(task, 'in', **fields)
    if not private:
        COMP.event('received', f'{slack.name(by)} wrote', task=key_of(task), detail=said)
    return it


@ledger.listen
def _render(task: Task, it: Item, old: str | None) -> None:
    """Copies and warnings into the case thread; the cards and the agent's own lines are posted where they happen."""
    c = task.get('case')
    kind, st = it['kind'], it['state']
    if st in ('refused', 'failed', 'lost'):
        what = {'in': 'A message', 'final': 'The reply'}.get(kind, f"{NAME}'s {kind.replace('_', ' ')}")
        to = f' to {it["label"]}' if it.get('label') else ''
        note(task, f':warning: {what}{to} was {ledger.LABELS[st]}: {it.get("note") or "no reason given"}')
        return
    if not c or c.get('head') == 'errand':
        return
    if kind == 'in' and not it.get('private') and not it.get('first'):
        files = f'\n_{len(it["files"])} file(s)_' if it.get('files') else ''
        note(task, f'**{it["label"]}:**\n' + quote(it['text']) + files, f'{it["label"]} wrote')
    elif kind == 'message' and it.get('to') == 'colleague' and st == 'sent':
        files = f'\n_With {len(it["files"])} file(s): {", ".join(it["files"])}_' if it.get('files') else ''
        held = f'\n:no_entry: Held back: {it["held"]}' if it.get('held') else ''
        note(task, f':outbox_tray: **{NAME} → {who(task)}:**\n{it["text"]}{files}{held}', f'Sent to {who(task)}')
    elif kind == 'final' and st == 'sent' and it.get('to') == 'thread':  # shared: the colleague read it there
        note(task, f'**{NAME} → {who(task)}:**\n{it["text"]}', f'{NAME} replied to {who(task)}')


def ask(task: Task, text: str, files: list[Json] | None, ts: str) -> None:
    """The owner talks to the companion about a case: privately, answered in the case thread only."""
    c = of(task)
    if not c:
        return
    if machine.running(task):
        queue(task, {'by': OWNER, 'text': text, 'files': files, 'ts': ts})
        slack.post(
            *c, 'Queued', md=f':hourglass_flowing_sand: {NAME} is still answering {who(task)}; it reads this next.'
        )
        return
    waiting = ledger.pending(task, 'approval')
    msg = prompts.owner_private(
        slack.name(OWNER),
        who(task),
        prompts.outbox(task['outbox']),
        slack.ask(text).strip(),
        waiting[-1].get('action', '') if waiting else '',
    )
    paths = slack.download(files, f'{task["channel"]}-{task["thread_ts"].replace(".", "")}')
    if paths:
        msg += '\n\nFiles (saved for you):\n' + '\n'.join(f'- {p}' for p in paths)
    res = t3.send(task['thread'], msg)
    if not res.get('ok'):
        slack.post(*c, 'Could not ask', md=f":warning: I couldn't pass that on: {t3.error_text(res)}")
        return
    slack.react(c[0], ts, 'eyes')
    heard(task, OWNER, text, files, private=True)
    COMP.event('private', f'You asked {NAME}', task=key_of(task), detail=slack.ask(text).strip())
    with lock:
        now = now_iso()
        machine.set_asking(task, False)
        machine.begin_turn(task, 'owner', 'case')
        task.update(
            {
                'burst_start': now,
                'step_from': now,
                'ended': '',
                'trigger_ts': ts,
                'seen_ts': ts,
                'quiet_since': 0,
                'options': {},
                'last_status': '',
                'last_status_at': 0,
            }
        )
        ts_line = slack.note_only(*c, THINKING)
        task['line'] = {'ch': c[0], 'ts': ts_line, 'since': time.time()} if ts_line else None
    save()


def queue(task: Task, item: Queued) -> None:
    task.setdefault('queue', []).append(item)
    save()


def next_in_line(task: Task) -> Queued | None:
    """After a turn: the oldest message that waited for it, or None."""
    q = task.get('queue') or []
    return q.pop(0) if q else None


def deliver(task: Task, it: Item, ok: Sequence[str] = (), refused: Sequence[str] = ()) -> None:
    """A ledger message for the colleague: into their thread at once. ok / refused: its files, through the gate."""
    if refused:
        it['held'] = ', '.join(refused)
    if not slack.post(
        task['channel'], task['thread_ts'], first_sentence(no_emoji(it['text']), 200) or 'Message', md=it['text']
    ):
        ledger.move(task, it, 'failed', note='Slack did not take the message')
        return
    if ok:
        slack.upload(task['channel'], task['thread_ts'], ok)
    ledger.move(task, it, 'sent')
    COMP.event('sent', f'Message to {who(task)}', task=key_of(task), to=who(task), detail=it['text'])
