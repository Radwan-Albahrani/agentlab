"""The gate: the agent never sends anything itself. It leaves things in /workspace/.companion/outbox/<task>/ and the companion
picks them up on every poll:
  approval.json    a sensitive change it prepared            -> Approve / Reject (files previewed first)
  credential.json  a temporary first-login password           -> Send login / Don't send (removed at once)
  manifest.json    files and/or a reply, written LAST         -> files to the owner's DM, the reply to whoever asked
  post.json        a message or poll for a channel            -> preview with Post it / Don't post (see posts)
  poll-change.json the owner's change to an open poll         -> applied at once (see polls.change)
  review.json      a finished pull request review, written LAST -> posted on GitHub as the App (see reviews)
Files only leave if they are inside that folder, of a document/image type, and under the size cap."""

import json
import os
import time

from . import errands, polls, posts, reviews, slack
from .config import COMP, FILES, OWNER, log
from .state import key, save

OUTBOX = os.path.join(FILES, 'outbox')
DELIVER_TYPES = {'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.csv', '.xlsx', '.xls', '.docx', '.doc', '.zip'}
DELIVER_MAX = 50 * 1024 * 1024  # per file


def gate(box, names):
    """Which of these files may leave: inside this errand's outbox, an allowed type, under the size cap."""
    ok, refused = [], []
    for f in names:
        p = os.path.realpath(os.path.join(box, os.path.basename(str(f))))
        if not p.startswith(os.path.realpath(box) + os.sep) or not os.path.isfile(p):
            refused.append(f'{f} (missing)')
        elif os.path.splitext(p)[1].lower() not in DELIVER_TYPES:
            refused.append(f'{os.path.basename(p)} (file type not allowed)')
        elif os.path.getsize(p) > DELIVER_MAX:
            refused.append(f'{os.path.basename(p)} (over 50 MB)')
        else:
            ok.append(p)
    return ok, refused


def _take(path):
    """A JSON file the agent finished writing, or None (missing or still being written)."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except ValueError:
        return None


def tick(task):
    if not task.get('outbox'):
        return
    box = os.path.join(OUTBOX, task['outbox'])
    a = _take(os.path.join(box, 'approval.json'))
    if a is not None:
        os.replace(os.path.join(box, 'approval.json'), os.path.join(box, f'approval-{int(time.time())}.json'))
        errands.ask_approval(task, a)
    _preview(task, box)
    c = _take(os.path.join(box, 'credential.json'))
    if c is not None:
        os.remove(os.path.join(box, 'credential.json'))  # the password lives only in the companion's memory from here
        errands.ask_credential(task, c)
    p = _take(os.path.join(box, 'post.json'))
    if p is not None:
        os.replace(os.path.join(box, 'post.json'), os.path.join(box, f'post-{int(time.time())}.json'))
        posts.offer(task, p)
    c = _take(os.path.join(box, 'poll-change.json'))
    if c is not None:
        os.replace(os.path.join(box, 'poll-change.json'), os.path.join(box, f'poll-change-{int(time.time())}.json'))
        polls.change(c, task)
    r = _take(os.path.join(box, 'review.json'))
    if r is not None and task.get('review'):
        os.replace(os.path.join(box, 'review.json'), os.path.join(box, f'review-{int(time.time())}.json'))
        reviews.publish(task, box, r)
    m = _take(os.path.join(box, 'manifest.json'))
    if m is not None:
        os.replace(
            os.path.join(box, 'manifest.json'), os.path.join(box, f'delivered-{int(time.time())}.json')
        )  # never twice
        _deliver(task, box, m)


def _preview(task, box):
    """Attach to the approval thread exactly the files that would be sent, so the owner sees them before tapping."""
    a = task.get('approval') or {}
    if not a or a.get('decided') or a.get('previewed'):
        return
    names = a.get('files') or (
        sorted(f for f in os.listdir(box) if os.path.splitext(f)[1].lower() in DELIVER_TYPES)
        if os.path.isdir(box)
        else []
    )
    a['previewed'] = True
    ok, refused = gate(box, names)
    if ok:
        slack.upload(
            task['channel'],
            task['thread_ts'],
            ok,
            f':mag: Preview: {len(ok)} file{"s" if len(ok) != 1 else ""} that will go out if you approve'
            + (f' ({len(refused)} would be held back: {", ".join(refused)})' if refused else ''),
        )
    save()


def _deliver(task, box, m):
    """Files go to the owner's DM (in the errand thread when it is one); a reply goes to whoever asked."""
    ok, refused = gate(box, m.get('files') or [])
    ch, tts = task['channel'], task['thread_ts']
    link = slack.permalink(ch, tts)
    what = str(m.get('what') or task.get('title') or 'Files')[:200]
    who = str(m.get('for') or '')[:80]
    head = f':package: *{what}*' + (f' (for {who})' if who else '') + (f'\n<{link}|From this thread>' if link else '')
    if refused:
        head += '\n:no_entry: Held back: ' + ', '.join(refused)
    dm = slack.dm_owner()
    in_thread = tts if ch == dm else None
    if ok:
        slack.upload(dm, in_thread, ok, head)
    elif refused:  # nothing deliverable: only worth a line if something was held
        slack.post(dm, in_thread, what, md=head)
    if dm != ch and (ok or refused):
        slack.note_only(
            ch,
            tts,
            f":package: Sent {len(ok)} file{'s' if len(ok) != 1 else ''} to {slack.name(OWNER)}'s DM"
            + (f' ({len(refused)} held back)' if refused else ''),
        )
    if m.get('reply') and task.get('requester'):  # an answer for whoever asked (no approval needed)
        approved = task.pop('reply_pending', None) is not None  # replaces the one stored at approval: one reply only
        errands.reply_requester(task, str(m['reply'])[:3000], ok, approved=approved)
    log('outbox delivered', task.get('outbox'), len(ok), 'files,', len(refused), 'held')
    if ok or refused:
        COMP.event(
            'files',
            f'{len(ok)} file{"s" if len(ok) != 1 else ""} to you: {what}',
            task=key(ch, tts),
            to=slack.name(OWNER),
            ok=not refused,
            detail=('held back: ' + ', '.join(refused)) if refused else ', '.join(os.path.basename(p) for p in ok),
        )
