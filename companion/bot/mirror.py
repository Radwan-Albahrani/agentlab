"""A case's mirror: the colleague's thread, copied message by message into the owner's case thread, so the owner
reads exactly what was said there, by whom, where and when: the colleague's words, the companion's replies, anyone
else's, and their files. A copy is never a summary.

Slack is the source of truth. sync() reads the whole thread and brings the copies in line with it (new messages
copied in order, edits applied, deletions shown), so running it again changes nothing. It runs whenever the thread
changes: a Slack event there (routing.route -> noticed), the companion's own posts, edits and uploads there
(slack.on_change), and a sweep of live threads (main.watch_mirrors) for anything those missed. Each copy is a record
in its own state (fsm.COPY), and its files in theirs (fsm.ATTACHMENT)."""

import hashlib
import json
import re
import threading
import time

from . import attachments, jobs, machine, slack
from .config import NAME, log
from .fsm import ATTACHMENT, COPY
from .shapes import Attachment, Copy, CopyState, Json, Mirror, Task
from .state import key_of, lock, save, state
from .text import first_sentence
from .when import say

SWEEP_EVERY = 60
ALIVE = 24 * 3600  # a thread quiet this long is no longer swept; its next message syncs it again
SKIPPED = ('channel_join', 'channel_leave', 'group_join', 'group_leave')  # Slack's notices, not anyone's words
ACTING = ('actions', 'input')  # buttons and inputs belong to the original: a copy can't act for it
MAX_BLOCKS = 50
MENTION = re.compile(r'<@([A-Z][A-Z0-9_]*)(?:\|[^>]*)?>')
SPECIAL = re.compile(r'<!(here|channel|everyone)(?:\|[^>]*)?>')
GROUP = re.compile(r'<!subteam\^[A-Z0-9]+(?:\|([^>]*))?>')

_busy: dict[str, bool] = {}  # task key -> another sync was asked for while one ran
_guard = threading.Lock()


def follows(task: Task) -> bool:
    """Is the task's thread mirrored: a case the owner follows from a thread of their own (an errand's is theirs)."""
    c = task.get('case')
    return c is not None and c['head'] != 'errand' and (c['ch'], c['ts']) != (task['channel'], task['thread_ts'])


def begin(task: Task) -> None:
    """A new case: the mirror copies the whole thread, from its first message."""
    task['mirror'] = {'since': '', 'latest': 0.0, 'copies': {}}


def _task_at(channel: str, ts: str) -> Task | None:
    """The mirrored task whose thread is at `ts`, or holds the message `ts`."""
    for t in list(state['tasks'].values()):
        if t.get('channel') != channel or not follows(t):
            continue
        m = t.get('mirror')
        if t['thread_ts'] == ts or (m is not None and ts in m['copies']):
            return t
    return None


def noticed(ev: Json) -> None:
    """Any Slack message event (new, edited, deleted; anyone's, the companion's too): sync the thread it is in."""
    msg = ev.get('message') or ev.get('previous_message') or ev
    for ts in (msg.get('thread_ts'), msg.get('ts'), ev.get('deleted_ts')):
        task = _task_at(ev.get('channel', ''), ts) if ts else None
        if task:
            jobs.run_later(sync, task)
            return


@slack.on_change
def _ours(channel: str, ts: str) -> None:
    """The companion posted, edited or uploaded something: if it is in a mirrored thread, sync it now."""
    task = _task_at(channel, ts) if ts else None
    if task:
        jobs.run_later(sync, task)


def sweep() -> None:
    """Sync every live mirrored thread: a running turn, or a message within ALIVE."""
    now = time.time()
    for t in list(state['tasks'].values()):
        m = t.get('mirror')
        if follows(t) and m is not None and (machine.running(t) or now - m['latest'] < ALIVE):
            sync(t)


def sync(task: Task) -> None:
    """Bring the case's copies in line with the thread. One sync per task at a time; one asked for meanwhile runs
    right after."""
    k = key_of(task)
    with _guard:
        if k in _busy:
            _busy[k] = True
            return
        _busy[k] = False
    try:
        again = True
        while again:
            _sync(task)
            with _guard:
                again, _busy[k] = _busy[k], False
    finally:
        with _guard:
            _busy.pop(k, None)


def _sync(task: Task) -> None:
    if not follows(task):
        return
    msgs = slack.replies(task['channel'], task['thread_ts'])
    if msgs is None:
        return
    with lock:
        m = task.get('mirror')
        if m is None:  # a case from before the mirror: it copies what comes from now on
            m = {'since': max((x['ts'] for x in msgs), key=float, default=''), 'latest': 0.0, 'copies': {}}
            task['mirror'] = m
        m['latest'] = max([m['latest'], *(float(x['ts']) for x in msgs)])
    here = _place(task)
    there = _where(task)
    present = {x['ts'] for x in msgs}
    for msg in msgs:
        ts = msg['ts']
        if (m['since'] and float(ts) <= float(m['since'])) or msg.get('subtype') in SKIPPED:
            continue
        c = m['copies'].get(ts)
        if msg.get('subtype') == 'tombstone':  # deleted, its replies kept
            if c and not COPY.is_(c['state'], 'deleted'):
                _deleted(here, c)
        elif c is None or COPY.is_(c['state'], 'failed'):
            if not _copy(task, m, here, there, msg, c):
                break  # Slack refuses: the rest wait for the next sync, so the copies keep the thread's order
        elif not COPY.is_(c['state'], 'deleted') and _sig(msg) != c['sig']:
            _edited(task, here, there, msg, c)
    for ts, c in list(m['copies'].items()):
        if ts not in present and not COPY.is_(c['state'], 'deleted'):
            _deleted(here, c)
    save()


def _place(task: Task) -> tuple[str, str]:
    c = task.get('case')
    assert c, 'a mirror needs a case'
    return c['ch'], c['ts']


def _where(task: Task) -> str:
    ch = task['channel']
    name = slack.channel_name(ch)
    return f'#{name}' if name else (f'DM with {NAME}' if ch.startswith('D') else 'a private conversation')


def _link(task: Task, ts: str) -> str:
    """The message's own link: a reply's opens its thread."""
    url = slack.link(task['channel'], ts)
    return f'{url}?thread_ts={task["thread_ts"]}&cid={task["channel"]}' if url and ts != task['thread_ts'] else url


def _sig(msg: Json) -> str:
    """What the message says, as its copy shows it: text, blocks, attachments (not link previews, which Slack adds
    later) and files. A change is an edit."""
    notes = [a.get('text') or a.get('fallback') for a in msg.get('attachments') or [] if not a.get('from_url')]
    said = [msg.get('text'), msg.get('blocks'), notes, [f.get('id') for f in msg.get('files') or []]]
    return hashlib.sha1(json.dumps(said, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _who(msg: Json) -> tuple[str, str]:
    """(name, avatar URL or '') of whoever wrote the message: a person, the companion, or another app."""
    user = msg.get('user')
    profile = msg.get('bot_profile') or {}
    icon = (profile.get('icons') or {}).get('image_48', '')
    if user and user == slack.bot_user():
        return NAME, icon
    if user and not msg.get('bot_id'):
        return slack.name(user), slack.avatar(user)
    return profile.get('name') or msg.get('username') or 'An app', icon


def _esc(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _head(task: Task, there: str, msg: Json, mark: str = '') -> Json:
    """The copy's first line: avatar, who, where (a link to the message itself), when, and an edit or deletion."""
    name, avatar = _who(msg)
    at = int(float(msg['ts']))
    when = f'<!date^{at}^{{date_short_pretty}} at {{time}}|{say(at, "stamp")}>'
    link = _link(task, msg['ts'])
    line = f'*{_esc(name)}*  ·  ' + (f'<{link}|{there}>' if link else there) + f'  ·  {when}'
    elements: list[Json] = [{'type': 'image', 'image_url': avatar, 'alt_text': name}] if avatar else []
    elements.append({'type': 'mrkdwn', 'text': line + (f'  ·  _{mark}_' if mark else '')})
    return {'type': 'context', 'elements': elements}


def _plain(text: str) -> str:
    """Mentions as names: a copy notifies no one, so @-mentions become plain @Name text."""
    text = MENTION.sub(lambda m: '@' + slack.name(m.group(1)), text)
    text = SPECIAL.sub(r'@\1', text)
    return GROUP.sub(lambda m: m.group(1) or '@group', text)


def _quiet(node: object) -> object:
    """Blocks as they are, mentions made plain (rich text's user, usergroup and broadcast elements too)."""
    if isinstance(node, list):
        return [_quiet(n) for n in node]
    if not isinstance(node, dict):
        return node
    kind = node.get('type')
    if kind == 'user' and 'user_id' in node:
        return {'type': 'text', 'text': '@' + slack.name(node['user_id']), 'style': {'bold': True}}
    if kind == 'usergroup':
        return {'type': 'text', 'text': '@group', 'style': {'bold': True}}
    if kind == 'broadcast':
        return {'type': 'text', 'text': '@' + str(node.get('range') or 'here'), 'style': {'bold': True}}
    return {k: _plain(v) if k == 'text' and isinstance(v, str) else _quiet(v) for k, v in node.items()}


def _sections(text: str) -> list[Json]:
    return [
        {'type': 'section', 'text': {'type': 'mrkdwn', 'text': text[i : i + 3000]}} for i in range(0, len(text), 3000)
    ]


def _body(msg: Json) -> list[Json]:
    """The message's content exactly: its own blocks (rich text keeps every bit of formatting), else its text; then
    what its attachments say (not link previews)."""
    out: list[Json] = [b for b in msg.get('blocks') or [] if b.get('type') not in ACTING]
    if not out and msg.get('text'):
        out = _sections(msg['text'])
    for a in msg.get('attachments') or []:
        said = '' if a.get('from_url') else a.get('text') or a.get('fallback') or ''
        if said:
            out += _sections('\n'.join(f'>{line}' for line in said.splitlines()))
    quiet = _quiet(out)
    assert isinstance(quiet, list)
    return quiet[: MAX_BLOCKS - 2]


def _plain_body(msg: Json) -> list[Json]:
    """The words alone, for when Slack refuses the blocks."""
    return _sections(_plain(msg.get('text') or '')) if msg.get('text') else []


def _summary(text: str, msg: Json) -> str:
    """Notification text: 'Salah: the first sentence'."""
    words = first_sentence(slack.readable(_plain(msg.get('text') or '')), 150)
    n = len(msg.get('files') or [])
    return f'{text}: {words}' if words else f'{text} sent {n} file{"s" if n != 1 else ""}' if n else text


def _files_line(files: list[Attachment]) -> list[Json]:
    """A line naming the files that didn't come through, and why."""
    missed = [a for a in files if not ATTACHMENT.is_(a['state'], 'sent', 'ready')]
    if not missed:
        return []
    said = ' · '.join(f'{a["name"]} {a["state"]}' + (f' ({a["note"]})' if a['note'] else '') for a in missed)
    return [{'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': f':paperclip: _{_esc(said)}_'}]}]


def _mrkdwn(blocks: list[Json], plain: list[Json]) -> str:
    """The copy as one mrkdwn comment (an upload Slack won't take blocks for): its head line, then the words."""
    head = blocks[0]['elements'][-1]['text']
    return '\n'.join([head, *(b['text']['text'] for b in plain)])[:4000]


def _post(here: tuple[str, str], text: str, blocks: list[Json], plain: list[Json], files: list[Attachment]) -> str:
    """Post a copy, files and all: its ts ('' when Slack doesn't say where an upload landed). Raises when Slack takes
    neither the blocks nor the plain words."""
    ready = [a for a in files if ATTACHMENT.is_(a['state'], 'ready')]
    uploads = [{'file': a['path'], 'filename': a['name']} for a in ready]
    client = slack.app.client
    for as_blocks in (True, False) if ready else ():
        try:
            if as_blocks:
                shown = json.dumps(blocks + _files_line(files))
                r = client.files_upload_v2(channel=here[0], thread_ts=here[1], file_uploads=uploads, blocks=shown)
            else:
                comment = _mrkdwn(blocks, plain)
                r = client.files_upload_v2(
                    channel=here[0], thread_ts=here[1], file_uploads=uploads, initial_comment=comment
                )
        except Exception as e:  # blocks refused: the words as a comment; refused again: the files are named failed
            log('mirror upload failed:', e)
            for a in [] if as_blocks else ready:
                a['state'], a['note'] = ATTACHMENT.to(a['state'], 'failed'), f"Slack didn't take it: {str(e)[:120]}"
            continue
        for a in ready:
            a['state'] = ATTACHMENT.to(a['state'], 'sent')
        return slack.landed(here[0], r)
    error: Exception | None = None
    for b in (blocks, blocks[:1] + plain):
        try:
            r = slack.app.client.chat_postMessage(
                channel=here[0],
                thread_ts=here[1],
                text=text[:3000],
                blocks=b + _files_line(files),
                unfurl_links=False,
                unfurl_media=False,
            )
            return str(r['ts'])
        except Exception as e:
            log('mirror copy refused:', e)
            error = e
    raise RuntimeError(str(error)[:200])


def _folder(task: Task) -> str:
    return 'mirror/' + re.sub(r'[^\w.-]+', '_', key_of(task))


def _copy(task: Task, m: Mirror, here: tuple[str, str], there: str, msg: Json, c: Copy | None) -> bool:
    """A message not copied yet (or whose copy failed): copy it. False when Slack refused it."""
    name, _ = _who(msg)
    files = attachments.fetched(msg.get('files') or [], _folder(task))
    outcome: CopyState = 'copied'
    ts = note = ''
    try:
        ts = _post(here, _summary(name, msg), [_head(task, there, msg), *_body(msg)], _plain_body(msg), files)
    except Exception as e:
        outcome, note = 'failed', str(e)[:200]
    with lock:
        m['copies'][msg['ts']] = {
            'ts': msg['ts'],
            'who': name,
            'copy': ts,
            'state': COPY.to(c['state'], outcome) if c else COPY.first(outcome),
            'sig': _sig(msg),
            'files': files,
            'note': note,
        }
    return outcome == 'copied'


def _edited(task: Task, here: tuple[str, str], there: str, msg: Json, c: Copy) -> None:
    """The message changed: its copy shows it as it is now (marked edited when Slack marks it: a person's edit, not an
    app's update); a copy Slack won't change is posted again."""
    name, _ = _who(msg)
    blocks = [_head(task, there, msg, 'edited' if msg.get('edited') else ''), *_body(msg)]
    same_files = [f.get('name') for f in msg.get('files') or []] == [a['name'] for a in c['files']]
    files = c['files'] if same_files else attachments.fetched(msg.get('files') or [], _folder(task))
    ts = c['copy'] if same_files else ''
    if ts:
        try:
            slack.app.client.chat_update(channel=here[0], ts=ts, text=_summary(name, msg)[:3000], blocks=blocks)
        except Exception as e:
            log('mirror edit refused, copying again:', e)
            ts = ''
    if not ts:
        try:
            ts = _post(here, _summary(name, msg), blocks, _plain_body(msg), files if not same_files else [])
        except Exception as e:
            log('mirror edit not copied:', e)
            return  # the signature stays old: the next sync tries again
    with lock:
        c.update({'copy': ts or c['copy'], 'state': COPY.to(c['state'], 'edited'), 'sig': _sig(msg), 'files': files})


def _deleted(here: tuple[str, str], c: Copy) -> None:
    """The message is gone: its copy says so (or, never copied, it is just marked)."""
    line = f'*{_esc(c["who"])}* deleted this message'
    gone = [{'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': f':wastebasket: _{line}_'}]}]
    if COPY.is_(c['state'], 'copied', 'edited'):
        try:
            if c['copy']:
                slack.app.client.chat_update(
                    channel=here[0], ts=c['copy'], text=f'{c["who"]} deleted a message', blocks=gone
                )
            else:
                slack.app.client.chat_postMessage(
                    channel=here[0], thread_ts=here[1], text=f'{c["who"]} deleted a message', blocks=gone
                )
        except Exception as e:
            log('mirror deletion not shown:', e)
            return  # the next sync tries again
    with lock:
        c['state'] = COPY.to(c['state'], 'deleted')
