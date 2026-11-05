"""The gate: the agent never sends anything itself; its outbox/<task>/ JSON files are picked up here each poll."""

import json
import os
import time

from . import errands, polls, posts, reviews, slack
from .config import COMP, FILES, OWNER, log
from .state import key, save

OUTBOX = os.path.join(FILES, 'outbox')
DELIVER_TYPES = {
    '.pdf', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4', '.mov', '.webm',
    '.csv', '.xlsx', '.xls', '.docx', '.doc', '.txt', '.md', '.zip',
}  # fmt: skip
DELIVER_MAX = 50 * 1024 * 1024  # bytes per file


def gate(box, names):
    """(ok paths, refused reasons): only files inside `box`, of an allowed type, under the size cap may leave."""
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
    """The parsed JSON file, or None if missing or still being written."""
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
        os.remove(os.path.join(box, 'credential.json'))  # the password must not stay on disk
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
        os.replace(os.path.join(box, 'manifest.json'), os.path.join(box, f'delivered-{int(time.time())}.json'))
        _deliver(task, box, m)


def _preview(task, box):
    """Upload to the approval thread the files that would be sent, once."""
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
    """Files into the task's own thread; the reply, if any, to whoever asked."""
    ok, refused = gate(box, m.get('files') or [])
    ch, tts = task['channel'], task['thread_ts']
    what = str(m.get('what') or task.get('title') or 'Files')[:200]
    head = f':package: *{what}*'
    if refused:
        head += '\n:no_entry: Held back: ' + ', '.join(refused)
    if ok:
        slack.upload(ch, tts, ok, head)
    elif refused:
        slack.post(ch, tts, what, md=head)
    where = slack.channel_name(ch)
    if m.get('reply') and task.get('requester'):
        approved = task.pop('reply_pending', None) is not None
        errands.reply_requester(task, str(m['reply'])[:3000], ok, approved=approved)
    log('outbox delivered', task.get('outbox'), len(ok), 'files,', len(refused), 'held')
    if ok or refused:
        COMP.event(
            'files',
            f'{len(ok)} file{"s" if len(ok) != 1 else ""} in the thread: {what}',
            task=key(ch, tts),
            to=f'#{where}' if where else slack.name(OWNER),
            ok=not refused,
            detail=('held back: ' + ', '.join(refused)) if refused else ', '.join(os.path.basename(p) for p in ok),
        )
