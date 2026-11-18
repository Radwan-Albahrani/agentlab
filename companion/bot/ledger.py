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
  state     see STATES: each kind starts in its first state and moves only along MOVES.
  to        who it is for: 'colleague', 'owner', 'thread', 'channel', 'people'; label is the human form ("#bugs").
  card      {ch, ts}: the message where the owner decides, while one is needed.
  ref       the item id an edit changes, or an approval a withdraw takes back."""

import contextlib
import json
import os
import threading
import time

from .config import COMP, FILES, log
from .state import key_of, save

STATES = {
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
}
MOVES = {
    'received': {'awaiting_owner', 'approved', 'sent', 'applied', 'refused', 'failed', 'dry_run'},
    'awaiting_owner': {'approved', 'sent', 'rejected', 'replaced', 'withdrawn', 'failed', 'lost'},
    'approved': {'sent', 'failed'},
}
OPEN = ('received', 'awaiting_owner', 'approved')  # not settled yet
LABELS = {  # how a state reads to people (receipts, case thread, hub)
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


_listeners = []  # fn(task, item, old_state): the case thread renders from here (cases.py)
_mute = threading.local()


def listen(fn):
    _listeners.append(fn)
    return fn


@contextlib.contextmanager
def muted():
    """Record without showing (a migration of what was already shown)."""
    _mute.on = True
    try:
        yield
    finally:
        _mute.on = False


def items(task):
    return task.setdefault('items', [])


def add(task, kind, state=None, **fields):
    """A new item in its kind's first state (or `state`, one of its kind's states)."""
    if kind not in STATES:
        raise IllegalMoveError(f'unknown kind {kind!r}')
    state = state or STATES[kind][0]
    if state not in STATES[kind]:
        raise IllegalMoveError(f'{kind} cannot start as {state}')
    now = time.time()
    it = {
        'id': f'{len(items(task)) + 1}',
        'kind': kind,
        'state': state,
        'at': now,
        'updated': now,
        'history': [[state, now, fields.get('note', '')]],
        **{k: v for k, v in fields.items() if v is not None},
    }
    items(task).append(it)
    _changed(task, it, None)
    return it


def move(task, it, state, note='', **fields):
    """Move `it` to `state` along MOVES; anything else raises IllegalMoveError."""
    old = it['state']
    if state not in STATES[it['kind']] or state not in MOVES.get(old, ()):
        raise IllegalMoveError(f'{it["kind"]} {it["id"]}: {old} -> {state}')
    now = time.time()
    it.update(state=state, updated=now, **fields)
    if note:
        it['note'] = note
    it['history'].append([state, now, note])
    _changed(task, it, old)
    return it


def get(task, item_id):
    return next((i for i in items(task) if i['id'] == str(item_id)), None)


def on_card(task, ts):
    """The item whose decision card is the message `ts`."""
    return next((i for i in items(task) if (i.get('card') or {}).get('ts') == ts), None)


def pending(task, kind=None):
    """Items waiting for the owner, oldest first."""
    return [i for i in items(task) if i['state'] == 'awaiting_owner' and (kind is None or i['kind'] == kind)]


def latest(task, kind, states=OPEN):
    return next((i for i in reversed(items(task)) if i['kind'] == kind and i['state'] in states), None)


def turn_items(task):
    """What the turn under way produced."""
    since = (task.get('turn') or {}).get('at', 0)
    return [i for i in items(task) if i['at'] >= since]


def _changed(task, it, old):
    task['items_rev'] = task.get('items_rev', 0) + 1
    for fn in [] if getattr(_mute, 'on', False) else _listeners:
        try:
            fn(task, it, old)
        except Exception as e:  # the record stands even if showing it failed
            log('ledger listener failed:', e)
    receipts(task)
    save()


def receipts(task):
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


SHOWN = (  # what the hub gets of an item; never cards, drafts' markup or file paths
    'by', 'to', 'label', 'text', 'files', 'private', 'note', 'ref', 'action', 'details', 'side', 'question', 'where',
    'held', 'history',
)  # fmt: skip


def rows(task):
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
            'data': {f: i[f] for f in SHOWN if i.get(f) not in (None, '', [])},
        }
        for i in items(task)
    ]


def publish(tasks):
    COMP.items([r for t in tasks for r in rows(t)])
