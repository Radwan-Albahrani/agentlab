"""A task's explicit states: who it is with (party), where the owner follows it (case), the turn under way (turn), and
what the hub shows (phase). Every change goes through the functions here; nothing is inferred from leftovers.

party  {kind, user}     owner      the owner's own task: answered in its thread
                         colleague  someone the owner lets use the companion
                         errand     someone who asked the owner; the companion acts as the owner
case   {ch, ts, head, mode}   where the owner follows a party's conversation (never for party owner)
         head  own      a message the companion posted in the owner's DM for it
               card     the requests channel's approval card in the owner's DM
               errand   the errand's own thread in the owner's DM (the task's thread is the case)
         mode  private  the colleague hears only what the agent sends them; its final message is the owner's
               shared   the agent answers in the thread the colleague is in (a review they asked for), copied here
turn   {n, by, place, state, outcome, at, ended}
         by       owner | colleague | decision | t3 (started in T3 directly) | system (a retry, a nudge)
         place    where the message the agent is answering was written, so where it is answered:
                    thread  the task's own thread (where the colleague, or the owner in public, wrote)
                    case    the owner's case thread (the owner, privately)
                  Its thinking line and side answers go there; so does its final message, except that a
                  colleague's turn in a private case ends with the owner (final_goes_to).
         state    running -> ended
         outcome  answered | asked | silent | nothing_to_do | failed | stopped (set when it ends)
         A task is running exactly while its turn is; nothing else says so.
question  bool: the agent waits on an answer to its question (asking / set_asking)
paused  {at, resumes_at, run, nudged} while a running turn waits out a usage limit (pause / unpause)
phase  derived from the three above plus the ledger and a usage-limit pause, stored for the hub:
         working | waiting_owner | waiting_answer | paused | answered | nothing_to_do | stopped | failed"""

import time

from . import ledger
from .config import OWNER, log
from .fsm import IllegalStateError
from .state import save

PARTIES = ('owner', 'colleague', 'errand')
HEADS = ('own', 'card', 'errand')
MODES = ('private', 'shared')
PLACES = ('thread', 'case')
TURN_BY = ('owner', 'colleague', 'decision', 't3', 'system')
OUTCOMES = ('answered', 'asked', 'silent', 'nothing_to_do', 'failed', 'stopped')
PHASES = ('working', 'waiting_owner', 'waiting_answer', 'paused', 'answered', 'nothing_to_do', 'stopped', 'failed')


def party_of(guest=None, requester=None):
    if requester:
        return {'kind': 'errand', 'user': requester}
    if guest and guest != OWNER:
        return {'kind': 'colleague', 'user': guest}
    return {'kind': 'owner', 'user': OWNER}


def party(task):
    return task.get('party') or {'kind': 'owner', 'user': OWNER}


def is_colleague(task):
    return party(task)['kind'] == 'colleague'


def set_party(task, kind, user):
    if kind not in PARTIES:
        raise IllegalStateError(f'party {kind!r}')
    old = party(task)['kind']
    if old not in ('owner', kind):
        raise IllegalStateError(f'party {old} -> {kind}')
    task['party'] = {'kind': kind, 'user': user}


def open_case(task, ch, ts, head, mode='private', md=None):
    if head not in HEADS or mode not in MODES:
        raise IllegalStateError(f'case {head}/{mode}')
    if party(task)['kind'] == 'owner':
        raise IllegalStateError('the owner needs no case for their own task')
    if task.get('case'):
        raise IllegalStateError('the task has a case already')
    task['case'] = {'ch': ch, 'ts': ts, 'head': head, 'mode': mode, **({'md': md} if md else {})}


def case_mode(task):
    return (task.get('case') or {}).get('mode', '')


def final_goes_to(task):
    """Where the agent's final message goes: 'case' (the owner, privately) or 'thread' (the task's own thread)."""
    c = task.get('case') or {}
    if not c or c['head'] == 'errand':  # the owner's own thread (an errand's thread is in the owner's DM)
        return 'thread'
    if c['mode'] == 'private' and turn(task).get('by') in ('colleague', 'decision', 'system'):
        return 'case'  # the colleague hears only what the agent sends them
    return place(task)


def turn(task):
    return task.get('turn') or {}


def begin_turn(task, by, place):
    """A new turn: whoever's message (or decision) the agent is now answering, and where it was written."""
    if by not in TURN_BY or place not in PLACES:
        raise IllegalStateError(f'turn by {by!r} at {place!r}')
    if place == 'case' and not task.get('case'):
        raise IllegalStateError('no case to answer in')
    t = turn(task)
    if t.get('state') == 'running':
        raise IllegalStateError(f'turn {t["n"]} is still running')
    task['turn'] = {
        'n': t.get('n', 0) + 1,
        'by': by,
        'place': place,
        'state': 'running',
        'outcome': '',
        'at': time.time(),
        'ended': 0,
    }
    settle(task)


def place(task):
    """Where the current (or last) turn is answered: 'thread' | 'case'."""
    return turn(task).get('place') or 'thread'


def retake_turn(task, by, place):
    """The running turn is taken over by a new message (`by`, written at `place`): it is answered there now."""
    if by not in TURN_BY or place not in PLACES:
        raise IllegalStateError(f'turn by {by!r} at {place!r}')
    if turn(task).get('state') != 'running':
        begin_turn(task, by, place)
        return
    task['turn'].update(by=by, place=place)


def end_turn(task, outcome):
    if outcome not in OUTCOMES:
        raise IllegalStateError(f'outcome {outcome!r}')
    t = turn(task)
    if t.get('state') != 'running':
        raise IllegalStateError('no turn is running')
    t.update(state='ended', outcome=outcome, ended=time.time())
    settle(task)


def running(task):
    return turn(task).get('state') == 'running'


def outcome(task):
    """How the last turn ended ('' while one runs)."""
    return turn(task).get('outcome') or ''


def owners_turn(task):
    return running(task) and turn(task).get('by') in ('owner', 't3') and bool(task.get('case'))


def asking(task):
    """The agent waits on an answer to a question it asked (in T3's record)."""
    return bool(task.get('question'))


def set_asking(task, asked):
    """The only way the question flag changes: the phase follows at once."""
    if asking(task) != asked:
        task['question'] = asked
        settle(task)


def paused(task):
    """The usage-limit pause of the running turn, {at, resumes_at, run, nudged}, or None."""
    return task.get('paused')


def pause(task, at, resumes_at, run):
    """The turn waits for T3 to resume the chat at the usage limit's reset (resumes_at: epoch, or None if unknown)."""
    if not running(task):
        raise IllegalStateError('only a running turn can pause')
    task['paused'] = {'at': at, 'resumes_at': resumes_at, 'run': run, 'nudged': 0}
    settle(task)


def unpause(task):
    """The pause ends (T3 resumed, or the wait is given up); False if there was none."""
    if not task.pop('paused', None):
        return False
    settle(task)
    return True


def phase_of(task):
    if ledger.pending(task):
        return 'waiting_owner'
    if running(task):
        if paused(task):
            return 'paused'
        return 'waiting_answer' if asking(task) else 'working'
    out = outcome(task) or 'answered'
    return {'asked': 'waiting_answer', 'silent': 'answered'}.get(out, out)


_phase_listeners = []  # fn(task) once its phase changed: the case head (cases.py)


def on_phase(fn):
    _phase_listeners.append(fn)
    return fn


def settle(task):
    """Recompute the stored phase; True when it changed."""
    p = phase_of(task)
    if p not in PHASES:
        raise IllegalStateError(f'phase {p!r}')
    if task.get('phase') == p:
        return False
    task['phase'] = p
    task.setdefault('phases', []).append([p, time.time()])
    del task['phases'][:-30]
    for fn in _phase_listeners:
        try:
            fn(task)
        except Exception as e:  # the state stands even if showing it failed
            log('phase listener failed:', e)
    save()
    return True


@ledger.listen
def _items_changed(task, it, old):
    if it['state'] == 'awaiting_owner' or old == 'awaiting_owner':
        settle(task)


def prepare_all(tasks):
    """After a restart: tasks saved before these states are converted once; a turn that is not running has no live
    thinking line."""
    for t in tasks:
        if 'turn' not in t:
            migrate(t)
        if 'place' not in t['turn']:  # saved before turns had a place: where it was being answered then
            t['turn']['place'] = 'case' if t['turn']['by'] in ('owner', 't3') and t.get('case') else 'thread'
        if not running(t):
            t['line'] = None
            t.pop('status_ts', None), t.pop('line_start', None)  # an old line of a turn that ended: nothing live
        settle(t)


OLD = (
    'guest', 'colleague', 'requester', 'approved', 'approval', 'post_draft', 'reply_draft', 'reply_pending',
    'cred_ask', 'told', 'posted', 'answer_to', 'active', 'outcome', 'sent', 'limit_checked',
)  # fmt: skip
OLD_OUTCOMES = {
    'answered': 'answered',
    'asked you': 'asked',
    'posted': 'answered',
    'nothing new to post': 'silent',
    'nothing needed': 'nothing_to_do',
    'failed': 'failed',
    'stopped': 'stopped',
}


def migrate(task):
    """One task saved before these states, converted: every old flag becomes the state it meant, then is gone."""
    task['party'] = party_of(task.get('guest') or task.get('colleague'), task.get('requester'))
    if task.get('colleague') and not task.get('guest'):
        task['party'] = {'kind': 'colleague', 'user': task['colleague']}
    old = task.pop('case', None)
    if task['party']['kind'] == 'errand':
        task['case'] = {'ch': task['channel'], 'ts': task['thread_ts'], 'head': 'errand', 'mode': 'private'}
    elif old:
        head = 'own' if old.get('own') else 'card'
        mode = 'shared' if task.get('colleague') and not task.get('guest') else 'private'
        task['case'] = {
            'ch': old['ch'],
            'ts': old['ts'],
            'head': head,
            'mode': mode,
            **({'md': old['md']} if old.get('md') else {}),
        }
    elif task['party']['kind'] == 'colleague' and isinstance(task.get('approved'), str) and task['approved']:
        ch = (task.get('approval') or {}).get('ch') or ''
        task['case'] = {'ch': ch, 'ts': task['approved'], 'head': 'card', 'mode': 'private'}
    by = 'owner' if task.get('answer_to') else 'colleague' if task['party']['kind'] != 'owner' else 'owner'
    live = bool(task.get('active'))
    task['turn'] = {
        'n': 1,
        'by': by,
        'place': 'case' if by == 'owner' and task.get('case') else 'thread',
        'state': 'running' if live else 'ended',
        'outcome': '' if live else OLD_OUTCOMES.get(task.get('outcome') or '', 'answered'),
        'at': 0,
        'ended': 0,
    }
    with ledger.muted():  # these happened already: recorded, not shown again
        try:
            _migrate_items(task)
        except (KeyError, TypeError, IndexError, IllegalStateError, ledger.IllegalMoveError) as e:
            # a record this conversion does not understand: its old cards are dropped, the task itself is kept
            log('migrate: old cards of', task.get('thread'), 'dropped:', type(e).__name__, e)
            task['items'] = []
    for k in OLD:
        task.pop(k, None)


def _migrate_items(task):
    """The old waiting slots and sent posts, as ledger items in the state they were in."""
    for m in task.get('sent') or []:  # posts to channels and DMs: kept so they can still be edited
        ledger.add(
            task, 'message', 'sent', to='channel', label=m['where'], text=m['text'], where=m['where'], msgs=m['msgs']
        )
    a = task.get('approval')
    if a:
        it = ledger.add(
            task,
            'approval',
            action=a.get('action', ''),
            reply=a.get('reply', ''),
            files=a.get('files') or [],
            card={'ch': a.get('ch') or task['channel'], 'ts': a.get('ts')},
            md=a.get('md', ''),
        )
        ledger.move(task, it, 'awaiting_owner')
        decided = {'approved': 'approved', 'rejected': 'rejected', 'replaced': 'replaced'}.get(a.get('decided') or '')
        if decided:
            ledger.move(task, it, decided)
        elif a.get('decided'):
            ledger.move(task, it, 'replaced', note=f'was {a["decided"]}')
    d = task.get('post_draft')
    if d:
        post = {k: d[k] for k in ('channel', 'to', 'poll', 'edit', 'where', 'msgs', 'text') if k in d}
        it = ledger.add(
            task,
            'edit' if d.get('edit') else 'message',
            to='people' if d.get('to') else 'channel',
            label=d.get('where') or '',
            text=d.get('text', ''),
            post=post,
            card={'ch': d.get('at') or task['channel'], 'ts': d['ts']},
            md=d.get('md', ''),
        )
        ledger.move(task, it, 'awaiting_owner')
    r = task.get('reply_draft')
    if r:
        it = ledger.add(
            task,
            'message',
            to='requester',
            text=r.get('text', ''),
            paths=r.get('files') or [],
            card={'ch': task['channel'], 'ts': r['ts']},
            md=r.get('md', ''),
        )
        ledger.move(task, it, 'awaiting_owner')
    if task.get('reply_pending'):
        it = ledger.add(task, 'message', to='requester', text=task['reply_pending'], after='turn')
        ledger.move(task, it, 'approved')
    c = task.get('cred_ask')
    if c:  # the password lived in memory only: it is gone
        it = ledger.add(task, 'credential', to='person', card={'ch': task['channel'], 'ts': c['ts']}, md=c['md'])
        ledger.move(task, it, 'awaiting_owner')
        ledger.move(task, it, 'lost', note='the companion restarted, so the password is gone')
