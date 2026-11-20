"""The gate: the agent never sends anything itself. It writes items to outbox/<task>/send.json; each poll they are
checked here, recorded in the ledger (ledger.py) and handed to the one module that acts on their type. What became of
each one is written back to outbox/<task>/receipts.json.

send.json: one item or a list. Every item names its "type", and a message its "to"; nothing has a default:
  {"type": "message", "to": "<who>", "text": "...", "files": [...], "poll": {...}}
       to: the colleague's or requester's name | "owner" | "thread" | "#channel" | a person's name | [names]
  {"type": "edit", "id": "<a message's id from receipts.json>", "text": "<the complete new text>"}
  {"type": "approval", "action": "...", "details": "...", "reply": "<errands: for the requester once done>",
   "files": [...]}
  {"type": "withdraw", "why": "..."}                       takes back the approval waiting
  {"type": "credential", "for", "service", "url", "username", "password", "note"}
  {"type": "poll_change", "poll": "<id>", ...the fields that change}
review.json is a PR review's own hand-over (reviews.py)."""

import json
import os
import re
import time
from typing import Any

from . import cases, errands, gate, ledger, machine, polls, posts, reviews, slack
from .config import FILES, OWNER, log
from .shapes import Item, Task
from .state import review_of

OUTBOX = os.path.join(FILES, 'outbox')
TYPES = ('message', 'edit', 'approval', 'withdraw', 'credential', 'poll_change')
CHANNEL_ID = re.compile(r'[CG][A-Z0-9]{6,}')


def _take(box: str, name: str) -> Any:
    """The parsed JSON file, moved aside so it is taken once; None if missing or still being written."""
    path = os.path.join(box, name)
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
    except ValueError:
        return None
    if name == 'send.json':
        os.remove(path)  # it may hold a password (credential); what it said lives on in the ledger
    else:
        os.replace(path, os.path.join(box, f'{name[:-5]}-{time.time_ns()}.json'))
    return data


def tick(task: Task) -> None:
    if not task.get('outbox'):
        return
    box = os.path.join(OUTBOX, task['outbox'])
    raw: list[Any] = []
    m = _take(box, 'send.json')
    if m is not None:
        raw += m if isinstance(m, list) else [m]
    for one in raw:
        take(task, box, one)
    r = _take(box, 'review.json') if review_of(task) else None
    if r is not None:
        reviews.publish(task, box, r)


def resolve(task: Task, to: object) -> tuple[str, str, str]:
    """(target, label, problem) for a message's "to"; the target is one of the ledger's `to` values."""
    p = machine.party(task)
    if isinstance(to, list):
        names = [str(x).strip() for x in to if str(x).strip()]
        return ('people', ', '.join(names), '') if names else ('', '', '"to" is an empty list')
    t = str(to or '').strip()
    if not t:
        return '', '', '"to" is required: the person, "owner", "thread", or "#channel"'
    low = t.lstrip('@').lower()
    if low == 'owner' or low == slack.name(OWNER).lower():
        return 'owner', slack.name(OWNER), ''
    if p['kind'] == 'colleague' and low in ('colleague', slack.name(p['user']).lower()):
        return 'colleague', slack.name(p['user']), ''
    if p['kind'] == 'errand' and low in ('requester', slack.name(p['user']).lower()):
        return 'requester', slack.name(p['user']), ''
    if low in ('thread', 'here'):
        if p['kind'] == 'colleague' and machine.case_mode(task) == 'private':
            return '', '', f'"thread" is {slack.name(p["user"])}\'s thread here: write their name as "to"'
        return 'thread', 'this thread', ''
    if t.startswith('#') or CHANNEL_ID.fullmatch(t) or t in {c['id'] for c in slack.channels()}:
        return 'channel', t if t.startswith('#') else f'<#{t}>', ''
    return 'people', t, ''


def take(task: Task, box: str, raw: object) -> None:
    """One item from the agent: checked, recorded, acted on."""
    if not isinstance(raw, dict):
        ledger.add(task, 'message', 'refused', note='an item must be a JSON object')
        return
    kind = str(raw.get('type') or '').strip().replace('-', '_')
    if kind not in TYPES:
        ledger.add(
            task,
            'message',
            'refused',
            text=str(raw.get('text') or '')[:300],
            note=f'"type" must be one of {", ".join(TYPES)}',
        )
        return
    if kind == 'withdraw':
        errands.withdraw(task, str(raw.get('why') or '').strip()[:300])
        return
    if kind == 'credential':
        errands.ask_credential(task, raw)
        return
    text = str(raw.get('text') or '').strip()[:3000]
    files = [os.path.basename(str(f)) for f in raw.get('files') or [] if str(f).strip()]
    if kind == 'message':
        target, label, problem = resolve(task, raw.get('to'))
        it = ledger.add(
            task, 'message', to=target, label=label, poll=raw.get('poll'), raw_to=raw.get('to'), text=text, files=files
        )
        if problem or (not text and not files and not raw.get('poll')):
            ledger.move(task, it, 'refused', note=problem or 'it has no text and no files')
            return
        _message(task, box, it)
    elif kind == 'edit':
        it = ledger.add(task, 'edit', ref=str(raw.get('id') or '').strip().lstrip('#'), text=text, files=files)
        posts.offer(task, it)
    elif kind == 'approval':
        it = ledger.add(
            task,
            'approval',
            action=str(raw.get('action') or '').strip()[:500],
            details=str(raw.get('details') or '').strip()[:3000],
            reply=str(raw.get('reply') or '').strip()[:3000],
            text=text,
            files=files,
        )
        if not it['action']:
            ledger.move(task, it, 'refused', note='an approval needs an "action"')
            return
        errands.ask_approval(task, it, box)
    else:
        it = ledger.add(task, 'poll_change', ref=str(raw.get('poll') or ''), change=raw, text=text, files=files)
        problem = polls.change(raw, task)
        ledger.move(task, it, 'refused' if problem else 'applied', note=problem)


def _message(task: Task, box: str, it: Item) -> None:
    ok, refused = gate.files(box, it.get('files') or [])
    to = it['to']
    if to == 'colleague':
        cases.deliver(task, it, ok, refused)
    elif to in ('owner', 'thread'):
        ch, tts = cases.owner_place(task) if to == 'owner' else (task['channel'], task['thread_ts'])
        md = it['text'] + ('\n:no_entry: Held back: ' + ', '.join(refused) if refused else '')
        if ok:
            slack.upload(ch, tts, ok, md or None)
        elif md:
            slack.post(ch, tts, it['text'][:150] or 'Files', md=md)
        ledger.move(task, it, 'sent', held=', '.join(refused) or None)
    elif to == 'requester':
        errands.offer_reply(task, it, ok, refused)
    else:
        posts.offer(task, it)
    log('outbox item', it['id'], it['kind'], to, it['state'])
