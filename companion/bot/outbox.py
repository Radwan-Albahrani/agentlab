"""The gate: the agent never sends anything itself; its outbox/<task>/ JSON files are picked up here each poll."""

import json
import os
import re
import time

from . import cases, errands, polls, posts, reviews, slack
from .config import COMP, FILES, NAME, OWNER, log
from .state import key_of, review_of, save

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
    m = _take(os.path.join(box, 'send.json'))
    if m is not None:
        os.replace(os.path.join(box, 'send.json'), os.path.join(box, f'send-{int(time.time())}.json'))
        for one in m if isinstance(m, list) else [m]:
            if isinstance(one, dict):
                _send(task, box, one)
    p = _take(os.path.join(box, 'post.json'))
    if p is not None:
        os.replace(os.path.join(box, 'post.json'), os.path.join(box, f'post-{int(time.time())}.json'))
        posts.offer(task, p)
    c = _take(os.path.join(box, 'poll-change.json'))
    if c is not None:
        os.replace(os.path.join(box, 'poll-change.json'), os.path.join(box, f'poll-change-{int(time.time())}.json'))
        polls.change(c, task)
    r = _take(os.path.join(box, 'review.json'))
    if r is not None and review_of(task):
        os.replace(os.path.join(box, 'review.json'), os.path.join(box, f'review-{int(time.time())}.json'))
        reviews.publish(task, box, r)
    m = _take(os.path.join(box, 'manifest.json'))
    if m is not None:
        os.replace(os.path.join(box, 'manifest.json'), os.path.join(box, f'delivered-{int(time.time())}.json'))
        _deliver(task, box, m)


CHANNEL_ID = re.compile(r'[CG][A-Z0-9]{6,}')


def _same(name, person):
    return bool(person) and name.lstrip('@').strip().lower() == person.lower()


def _send(task, box, m):
    """One message from send.json, routed by its "to": the colleague (a case), this thread, or a post elsewhere that
    the owner previews (posts.py). In a colleague's task no "to" means the colleague."""
    to = m.get('to') or ''
    one = to.strip() if isinstance(to, str) else ''
    guest = task.get('guest') and cases.who(task)
    if m.get('edit') or m.get('poll') or isinstance(to, list) or (one and one.lower() not in ('here', 'thread')):
        if guest and one and _same(one, guest) and not m.get('poll') and not m.get('edit'):
            cases.send(task, m, *gate(box, m.get('files') or []))
            return
        if guest and one and _same(one, slack.name(OWNER)):
            cases.note(task, f'**{NAME} → you:**\n' + str(m.get('text') or '').strip()[:3000])
            return
        p = {k: m[k] for k in ('text', 'poll', 'edit') if k in m}
        if isinstance(to, list):
            p['to'] = to
        elif one.startswith('#') or CHANNEL_ID.fullmatch(one):
            p.update(channel=one, new_message=True)
        elif one:
            p['to'] = one
        posts.offer(task, p)
        return
    if guest:
        cases.send(task, m, *gate(box, m.get('files') or []))
        return
    _deliver(task, box, {'files': m.get('files') or [], 'text': str(m.get('text') or '').strip()[:3000]})


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
            *errands.approver(task),
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
    head = m.get('text') or f':package: *{what}*'  # send.json "to": "here" carries a message, not a title
    if refused:
        head += '\n:no_entry: Held back: ' + ', '.join(refused)
    if ok:
        slack.upload(ch, tts, ok, head)
    elif refused or m.get('text'):
        slack.post(ch, tts, str(m.get('text') or what)[:150], md=head)
    where = slack.channel_name(ch)
    if m.get('reply') and task.get('requester'):
        approved = task.pop('reply_pending', None) is not None
        errands.reply_requester(task, str(m['reply'])[:3000], ok, approved=approved)
    log('outbox delivered', task.get('outbox'), len(ok), 'files,', len(refused), 'held')
    if ok or refused:
        COMP.event(
            'files',
            f'{len(ok)} file{"s" if len(ok) != 1 else ""} in the thread: {what}',
            task=key_of(task),
            to=f'#{where}' if where else slack.name(OWNER),
            ok=not refused,
            detail=('held back: ' + ', '.join(refused)) if refused else ', '.join(os.path.basename(p) for p in ok),
        )
