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
from collections.abc import Callable, Iterable
from typing import Literal, get_args

from . import ledger
from .config import OWNER, log
from .fsm import IllegalStateError
from .shapes import (
    Case,
    Head,
    Item,
    Mode,
    Outcome,
    Party,
    PartyKind,
    Pause,
    Phase,
    Place,
    Task,
    Turn,
    TurnBy,
)
from .state import save

PARTIES: tuple[PartyKind, ...] = get_args(PartyKind)
HEADS: tuple[Head, ...] = get_args(Head)
MODES: tuple[Mode, ...] = get_args(Mode)
PLACES: tuple[Place, ...] = get_args(Place)
TURN_BY: tuple[TurnBy, ...] = get_args(TurnBy)
OUTCOMES: tuple[Outcome, ...] = get_args(Outcome)
PHASES: tuple[Phase, ...] = get_args(Phase)


def party_of(guest: str | None = None, requester: str | None = None) -> Party:
    if requester:
        return {'kind': 'errand', 'user': requester}
    if guest and guest != OWNER:
        return {'kind': 'colleague', 'user': guest}
    return {'kind': 'owner', 'user': OWNER}


def party(task: Task) -> Party:
    return task.get('party') or {'kind': 'owner', 'user': OWNER}


def is_colleague(task: Task) -> bool:
    return party(task)['kind'] == 'colleague'


def set_party(task: Task, kind: PartyKind, user: str) -> None:
    if kind not in PARTIES:
        raise IllegalStateError(f'party {kind!r}')
    old = party(task)['kind']
    if old not in ('owner', kind):
        raise IllegalStateError(f'party {old} -> {kind}')
    task['party'] = {'kind': kind, 'user': user}


def open_case(task: Task, ch: str, ts: str, head: Head, mode: Mode = 'private', md: str | None = None) -> None:
    if head not in HEADS or mode not in MODES:
        raise IllegalStateError(f'case {head}/{mode}')
    if party(task)['kind'] == 'owner':
        raise IllegalStateError('the owner needs no case for their own task')
    if task.get('case'):
        raise IllegalStateError('the task has a case already')
    case: Case = {'ch': ch, 'ts': ts, 'head': head, 'mode': mode}
    if md:
        case['md'] = md
    task['case'] = case


def case_mode(task: Task) -> str:
    c = task.get('case')
    return c.get('mode', '') if c else ''


def final_goes_to(task: Task) -> Place:
    """Where the agent's final message goes: 'case' (the owner, privately) or 'thread' (the task's own thread)."""
    c = task.get('case')
    if not c or c['head'] == 'errand':  # the owner's own thread (an errand's thread is in the owner's DM)
        return 'thread'
    if c['mode'] == 'private' and turn(task).get('by') in ('colleague', 'decision', 'system'):
        return 'case'  # the colleague hears only what the agent sends them
    return place(task)


def turn(task: Task) -> Turn:
    return task.get('turn') or {}


def begin_turn(task: Task, by: TurnBy, place: Place) -> None:
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


def place(task: Task) -> Place:
    """Where the current (or last) turn is answered: 'thread' | 'case'."""
    return turn(task).get('place') or 'thread'


def retake_turn(task: Task, by: TurnBy, place: Place) -> None:
    """The running turn is taken over by a new message (`by`, written at `place`): it is answered there now."""
    if by not in TURN_BY or place not in PLACES:
        raise IllegalStateError(f'turn by {by!r} at {place!r}')
    if turn(task).get('state') != 'running':
        begin_turn(task, by, place)
        return
    task['turn'].update({'by': by, 'place': place})


def end_turn(task: Task, outcome: Outcome) -> None:
    if outcome not in OUTCOMES:
        raise IllegalStateError(f'outcome {outcome!r}')
    t = turn(task)
    if t.get('state') != 'running':
        raise IllegalStateError('no turn is running')
    t.update({'state': 'ended', 'outcome': outcome, 'ended': time.time()})
    settle(task)


def running(task: Task) -> bool:
    return turn(task).get('state') == 'running'


def outcome(task: Task) -> Outcome | Literal['']:
    """How the last turn ended ('' while one runs)."""
    return turn(task).get('outcome') or ''


def owners_turn(task: Task) -> bool:
    return running(task) and turn(task).get('by') in ('owner', 't3') and bool(task.get('case'))


def asking(task: Task) -> bool:
    """The agent waits on an answer to a question it asked (in T3's record)."""
    return bool(task.get('question'))


def set_asking(task: Task, asked: bool) -> None:
    """The only way the question flag changes: the phase follows at once."""
    if asking(task) != asked:
        task['question'] = asked
        settle(task)


def paused(task: Task) -> Pause | None:
    """The usage-limit pause of the running turn, {at, resumes_at, run, nudged}, or None."""
    return task.get('paused')


def pause(task: Task, at: float, resumes_at: float | None, run: str | None) -> None:
    """The turn waits for T3 to resume the chat at the usage limit's reset (resumes_at: epoch, or None if unknown)."""
    if not running(task):
        raise IllegalStateError('only a running turn can pause')
    task['paused'] = {'at': at, 'resumes_at': resumes_at, 'run': run, 'nudged': 0}
    settle(task)


def unpause(task: Task) -> bool:
    """The pause ends (T3 resumed, or the wait is given up); False if there was none."""
    if not task.pop('paused', None):
        return False
    settle(task)
    return True


def phase_of(task: Task) -> Phase:
    if ledger.pending(task):
        return 'waiting_owner'
    if running(task):
        if paused(task):
            return 'paused'
        return 'waiting_answer' if asking(task) else 'working'
    out = outcome(task) or 'answered'
    if out == 'asked':
        return 'waiting_answer'
    if out == 'silent':
        return 'answered'
    return out


PhaseListener = Callable[[Task], object]
_phase_listeners: list[PhaseListener] = []  # fn(task) once its phase changed: the case head (cases.py)


def on_phase[F: PhaseListener](fn: F) -> F:
    _phase_listeners.append(fn)
    return fn


def settle(task: Task) -> bool:
    """Recompute the stored phase; True when it changed."""
    p = phase_of(task)
    if p not in PHASES:
        raise IllegalStateError(f'phase {p!r}')
    if task.get('phase') == p:
        return False
    task['phase'] = p
    task.setdefault('phases', []).append((p, time.time()))
    del task['phases'][:-30]
    for fn in _phase_listeners:
        try:
            fn(task)
        except Exception as e:  # the state stands even if showing it failed
            log('phase listener failed:', e)
    save()
    return True


@ledger.listen
def _items_changed(task: Task, it: Item, old: str | None) -> None:
    if it['state'] == 'awaiting_owner' or old == 'awaiting_owner':
        settle(task)


def prepare_all(tasks: Iterable[Task]) -> None:
    """After a restart: a turn that is not running has no live thinking line, and each phase is recomputed."""
    for t in tasks:
        if not running(t):
            t['line'] = None
        settle(t)
