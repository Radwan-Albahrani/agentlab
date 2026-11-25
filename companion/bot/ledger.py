"""The ledger: every message in and out of a task, and everything waiting on the owner, as items with explicit states.

One list per task (task['items']). It is the only record of what was said, sent, refused or decided: the case thread in
the owner's DM, the agent's receipts file and the hub's Cases tab are all views of it.

Item: {id, kind, state, at, updated, history: [[state, at, note]], by, to, label, text, files, private, card, ref, note}
  kind      in          a message to the companion: from the colleague, or the owner's private word in a case
            final       the agent's final message of a turn (to the owner; in the owner's own task, their thread)
            message     something the agent sent or wants to send (send.json "message")
            edit        a change to a message it sent before
            approval    a sensitive step that needs the owner's OK
            credential  a first-login password to DM to someone
            poll_change a change to an open poll
            review      pull requests the agent hands to the review queue (text: their links)
  state     see STATES: each kind starts in its first state and moves only along MOVES.
  to        who it is for: 'colleague', 'owner', 'thread', 'channel', 'people'; label is the human form ("#bugs").
  card      {ch, ts}: the message where the owner decides, while one is needed.
  ref       the item id an edit changes, or an approval a withdraw takes back.
  attachments  an outgoing message's files, each in its own state (attachments.py, fsm.ATTACHMENT)."""

import contextlib
import json
import os
import threading
import time
from collections.abc import Callable, Collection, Iterable, Iterator
from typing import Literal, Unpack, get_args

from tables import ItemRow

from . import attachments
from .config import COMP, FILES, log
from .shapes import Item, ItemData, ItemFields, ItemKind, ItemState, Json, Task
from .state import key_of, save

STATES: dict[ItemKind, tuple[ItemState, ...]] = {
    'in': ('received',),
    'final': ('sent', 'silent'),
    'message': (
        'received',
        'awaiting_owner',
        'approved',
        'sent',
        'refused',
        'rejected',
        'replaced',
        'failed',
        'dry_run',
    ),
    'edit': ('received', 'awaiting_owner', 'approved', 'sent', 'refused', 'rejected', 'replaced', 'failed'),
    'approval': ('received', 'awaiting_owner', 'approved', 'rejected', 'replaced', 'withdrawn', 'refused'),
    'credential': ('received', 'awaiting_owner', 'sent', 'rejected', 'refused', 'failed', 'lost'),
    'poll_change': ('received', 'applied', 'refused'),
    'review': ('received', 'applied', 'refused'),
}
MOVES: dict[ItemState, set[ItemState]] = {
    'received': {'awaiting_owner', 'approved', 'sent', 'applied', 'refused', 'failed', 'dry_run'},
    'awaiting_owner': {'approved', 'sent', 'rejected', 'replaced', 'withdrawn', 'failed', 'lost'},
    'approved': {'sent', 'failed'},
}
OPEN: tuple[ItemState, ...] = ('received', 'awaiting_owner', 'approved')  # not settled yet
NEVER_WENT: tuple[ItemState, ...] = ('refused', 'rejected', 'replaced', 'withdrawn', 'failed', 'dry_run', 'lost')
LABELS: dict[ItemState, str] = {  # how a state reads to people (receipts, case thread, hub)
    'received': 'received',
    'awaiting_owner': 'waiting for the owner',
    'approved': 'approved',
    'sent': 'sent',
    'silent': 'nothing to say',
    'applied': 'applied',
    'refused': 'refused',
    'rejected': 'rejected by the owner',
    'replaced': 'replaced by a newer one',
    'withdrawn': 'withdrawn',
    'failed': 'failed',
    'dry_run': 'not sent (dry run)',
    'lost': 'lost (the companion restarted)',
}


class IllegalMoveError(ValueError):
    """A move the item's state machine does not allow: a bug, never something to work around."""


Listener = Callable[[Task, Item, str | None], object]
_listeners: list[Listener] = []  # fn(task, item, old_state): the case thread renders from here (cases.py)
_mute = threading.local()


def listen[F: Listener](fn: F) -> F:
    _listeners.append(fn)
    return fn


@contextlib.contextmanager
def muted() -> Iterator[None]:
    """Record without showing (a migration of what was already shown)."""
    _mute.on = True
    try:
        yield
    finally:
        _mute.on = False


def items(task: Task) -> list[Item]:
    return task.setdefault('items', [])


def add(task: Task, kind: ItemKind, state: ItemState | None = None, **fields: Unpack[ItemFields]) -> Item:
    """A new item in its kind's first state (or `state`, one of its kind's states)."""
    if kind not in STATES:
        raise IllegalMoveError(f'unknown kind {kind!r}')
    state = state or STATES[kind][0]
    if state not in STATES[kind]:
        raise IllegalMoveError(f'{kind} cannot start as {state}')
    now = time.time()
    it: Item = {
        'id': f'{len(items(task)) + 1}',
        'kind': kind,
        'state': state,
        'at': now,
        'updated': now,
        'history': [(state, now, fields.get('note', ''))],
    }
    it.update(fields)
    items(task).append(it)
    _changed(task, it, None)
    return it


def move(task: Task, it: Item, state: ItemState, note: str = '', **fields: Unpack[ItemData]) -> Item:
    """Move `it` to `state` along MOVES; anything else raises IllegalMoveError."""
    old = it['state']
    if state not in STATES[it['kind']] or state not in MOVES.get(old, ()):
        raise IllegalMoveError(f'{it["kind"]} {it["id"]}: {old} -> {state}')
    if state == 'sent' and attachments.ready(it):
        raise IllegalMoveError(f'{it["kind"]} {it["id"]}: sent while its files are still waiting to go')
    if state in NEVER_WENT:
        attachments.settle(it, 'withheld', LABELS[state])
    now = time.time()
    it.update({'state': state, 'updated': now})
    it.update(fields)
    if note:
        it['note'] = note
    it['history'].append((state, now, note))
    _changed(task, it, old)
    return it


def get(task: Task, item_id: str | int) -> Item | None:
    return next((i for i in items(task) if i['id'] == str(item_id)), None)


def on_card(task: Task, ts: str) -> Item | None:
    """The item whose decision card is the message `ts`."""
    return next((i for i in items(task) if 'card' in i and i['card']['ts'] == ts), None)


def pending(task: Task, kind: ItemKind | None = None) -> list[Item]:
    """Items waiting for the owner, oldest first."""
    return [i for i in items(task) if i['state'] == 'awaiting_owner' and (kind is None or i['kind'] == kind)]


def latest(task: Task, kind: ItemKind, states: Collection[ItemState] = OPEN) -> Item | None:
    return next((i for i in reversed(items(task)) if i['kind'] == kind and i['state'] in states), None)


def turn_items(task: Task) -> list[Item]:
    """What the turn under way produced."""
    since = (task.get('turn') or {}).get('at', 0)
    return [i for i in items(task) if i['at'] >= since]


def _changed(task: Task, it: Item, old: str | None) -> None:
    task['items_rev'] = task.get('items_rev', 0) + 1
    for fn in [] if getattr(_mute, 'on', False) else _listeners:
        try:
            fn(task, it, old)
        except Exception as e:  # the record stands even if showing it failed
            log('ledger listener failed:', e)
    receipts(task)
    save()


def receipts(task: Task) -> None:
    """outbox/<task>/receipts.json: what became of everything the agent handed over, for the agent to read."""
    if not task.get('outbox'):
        return
    box = os.path.join(FILES, 'outbox', task['outbox'])
    rows = [
        {
            'id': i['id'],
            'type': i['kind'],
            'to': i.get('label') or i.get('to') or '',
            'state': i['state'],
            'meaning': LABELS[i['state']],
            'note': i.get('note', ''),
            'text': (i.get('text') or '')[:120],
            'files': [{'name': a['name'], 'state': a['state'], 'why': a['note']} for a in i.get('attachments') or []],
        }
        for i in items(task)
        if i['kind'] not in ('in', 'final')
    ]
    try:
        os.makedirs(box, exist_ok=True)
        tmp = os.path.join(box, '.receipts.json')
        with open(tmp, 'w') as f:
            json.dump(rows, f, indent=1, ensure_ascii=False)
        os.replace(tmp, os.path.join(box, 'receipts.json'))
    except OSError as e:
        log('receipts not written:', e)


Shown = Literal[  # what the hub gets of an item; never cards, drafts' markup or file paths
    'by', 'to', 'label', 'text', 'files', 'private', 'note', 'ref', 'action', 'details', 'side', 'question', 'where',
    'history',
]  # fmt: skip
SHOWN: tuple[Shown, ...] = get_args(Shown)


def _shown(i: Item) -> Json:
    data: Json = {f: i[f] for f in SHOWN if i.get(f) not in (None, '', [])}
    if i.get('attachments'):  # each file's state, without its path
        data['attachments'] = [{'name': a['name'], 'state': a['state'], 'note': a['note']} for a in i['attachments']]
    return data


def rows(task: Task) -> list[ItemRow]:
    """The items as the hub stores them (companion.py `items` table)."""
    k = key_of(task)
    return [
        {
            'id': f'{k}#{i["id"]}',
            'task': k,
            'seq': int(i['id']),
            'kind': i['kind'],
            'state': i['state'],
            'at': i['at'],
            'data': _shown(i),
        }
        for i in items(task)
    ]


def publish(tasks: Iterable[Task]) -> None:
    COMP.items([r for t in tasks for r in rows(t)])
