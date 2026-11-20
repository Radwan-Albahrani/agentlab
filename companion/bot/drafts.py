"""Product-update drafts (product-updates/<id>/: update.md, images or a video, ready.json written last), previewed to
the owner."""

import copy
import json
import os
import re
import time
from collections.abc import Iterable

from slack_bolt import Ack
from slack_sdk import WebClient

from . import projects, prompts, slack, t3
from .config import AGENT_FILES, COMP, FILES, NAME, OWNER, log, publish_channel
from .fsm import DRAFT
from .shapes import Draft, Posted
from .slack import Json
from .state import lock, save, state
from .text import first_sentence, to_slack

DRAFTS = os.path.join(FILES, 'product-updates')
AGENT_DRAFTS = f'{AGENT_FILES}/product-updates'
IMAGE_REF = re.compile(r'^[ \t]*!\[[^\]]*\]\([^)]*\)[ \t]*\n?', re.M)


VIDEOS = ('.mp4', '.mov', '.webm')
MAX_MB = 200  # Slack takes up to 1 GB; a weekly update's video is 20-50 MB, so anything near this is a mistake
UPLOAD_TIMEOUT = 300  # seconds per upload call when a video is attached
SHARE_TRIES, SHARE_EVERY = 30, 2  # files.info polls for a video post's message, ~60 s: Slack processes videos first


def _files(d: str, meta: Json) -> tuple[str, list[str]]:
    """update.md without image lines, and the attachments: ready.json's "images" as given, else any videos then images."""
    videos = sorted(f for f in os.listdir(d) if f.lower().endswith(VIDEOS))
    imgs = meta.get('images') or videos + sorted(
        f for f in os.listdir(d) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))
    )
    with open(os.path.join(d, 'update.md'), encoding='utf-8') as f:
        text = f.read()
    text = re.sub(r'\n{3,}', '\n\n', IMAGE_REF.sub('', text)).strip()
    return text, [os.path.join(d, f) for f in imgs if os.path.isfile(os.path.join(d, f))]


def has_video(paths: Iterable[str]) -> bool:
    return any(p.lower().endswith(VIDEOS) for p in paths)


def _too_big(paths: Iterable[str]) -> str:
    """Why these can't be uploaded, or ''."""
    for p in paths:
        mb = os.path.getsize(p) / 2**20
        if mb > MAX_MB:
            return f'{os.path.basename(p)} is {mb:.0f} MB, over the {MAX_MB} MB upload cap. Make it smaller, then rewrite ready.json.'
    return ''


def _uploader() -> WebClient:
    """The bot client with a long timeout, for uploads that carry a video."""
    c = copy.copy(slack.app.client)
    c.timeout = UPLOAD_TIMEOUT
    return c


def _send(channel: str, text_md: str, images: list[str], thread_ts: str | None = None) -> Posted:
    """Post text plus screenshots (or a video) as one message; returns where it landed."""
    if images:
        if problem := _too_big(images):
            raise ValueError(problem)
        video = has_video(images)
        since = time.time() - 5
        r = (_uploader() if video else slack.app.client).files_upload_v2(
            channel=channel,
            thread_ts=thread_ts,
            initial_comment=to_slack(text_md, 3900),
            file_uploads=[{'file': p, 'filename': os.path.basename(p)} for p in images],
        )
        ts: str | None
        if thread_ts:
            ts = None
        elif video:  # a video's message shows up only once Slack has processed it
            ids = [f['id'] for f in ((r.get('files') if r else None) or []) if f.get('id')]
            ts = _shared_ts(channel, ids) or _find_upload(channel, since)
        else:
            ts = _find_upload(channel, since)
        return {'channel': channel, 'ts': ts, 'files': True}
    return {'channel': channel, 'ts': slack.post(channel, thread_ts, first_sentence(text_md, 300), md=text_md)}


def _shared_ts(channel: str, file_ids: list[str], tries: int = SHARE_TRIES) -> str | None:
    """The ts of the message an upload became, from files.info `shares`, filled in once Slack has the file ready."""
    for i in range(tries if file_ids else 0):
        for fid in file_ids:
            try:
                shares = slack.app.client.files_info(file=fid)['file'].get('shares') or {}
            except Exception as e:
                log('files.info failed:', fid, e)
                continue
            for kind in ('public', 'private'):
                for s in (shares.get(kind) or {}).get(channel) or []:
                    if s.get('ts'):
                        return s['ts']
        if i < tries - 1:
            time.sleep(SHARE_EVERY)
    return None


_refused: dict[str, float] = {}  # draft key -> the ready.json mtime already reported as too big to preview


def _find_upload(channel: str, since: float, tries: int = 5) -> str | None:
    """The ts of the bot's newest message with files since `since` (uploads don't return it)."""
    for i in range(tries):
        msgs = slack.app.client.conversations_history(channel=channel, oldest=f'{since:.6f}', limit=50)['messages']
        for m in msgs:
            if m.get('files') and m.get('user') == slack.bot_user():
                return m['ts']
        if i < tries - 1:
            time.sleep(1)  # the message appears shortly after the upload returns
    return None


def _edit(st: Draft, text_md: str) -> str:
    """Rewrite the posted message in place."""
    p: Posted = st.get('posted') or {'channel': publish_channel(), 'ts': None, 'files': True}
    if not p['ts']:
        thread = st['thread']
        p['ts'] = _find_upload(p['channel'], float(thread), tries=1) if thread else None
        if not p['ts']:
            raise RuntimeError(f"couldn't find the posted message in <#{p['channel']}>")
        st['posted'] = p
    if p.get('files'):
        slack.app.client.chat_update(channel=p['channel'], ts=p['ts'], text=to_slack(text_md, 3900))
    else:
        slack.update(p['channel'], p['ts'], first_sentence(text_md, 300), md=text_md)
    return p['channel']


def _buttons(key: str, rev: int, st: Draft, video: bool = False) -> list[Json]:
    if DRAFT.is_(st.get('status'), 'editing'):
        ch = st['posted']['channel'] if 'posted' in st else publish_channel()
        head, go, stop = f'*Edit of the post in <#{ch}>* · revision {rev}', 'Update the post', 'Keep it as it is'
        kept = 'the attachments (screenshots or video) stay' if video else 'the screenshots stay'
        foot = f'Updates the text in place; {kept} as posted. Reply here to change something.'
    else:
        head, go, stop = f'*Draft for <#{publish_channel()}>* · revision {rev}', 'Post to the channel', 'Discard'
        foot = 'Reply in this thread to change something.'
    return [
        {'type': 'section', 'text': {'type': 'mrkdwn', 'text': head}},
        slack.buttons(('draft_post', go, key, 'primary'), ('draft_discard', stop, key, None)),
        {'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': foot}]},
    ]


def tick() -> None:
    if not os.path.isdir(DRAFTS):
        return
    for key in sorted(os.listdir(DRAFTS)):
        d = os.path.join(DRAFTS, key)
        try:
            ready = os.path.join(d, 'ready.json')
            with open(ready) as f:
                meta = json.load(f)
            mtime = os.path.getmtime(ready)
        except (OSError, ValueError):
            continue
        rev = int(meta.get('revision', 1))
        st = state['drafts'].get(key)
        if st and mtime <= st.get('mtime', 0):
            continue
        if st and DRAFT.is_(st.get('status'), 'revising'):
            st['status'] = DRAFT.to(st.get('status'), 'editing')
        elif st and DRAFT.is_(
            st.get('status'), 'posted', 'discarded'
        ):  # a new run into a finished draft's folder: a new draft
            state['drafts'].pop(key)
            st = None
        if st and rev <= st['revision']:
            rev = st['revision'] + 1
        text_md, images = _files(d, meta)
        dm = slack.dm_owner()
        if problem := _too_big(images):
            if _refused.get(key) != mtime:
                _refused[key] = mtime
                slack.post(
                    dm,
                    st['thread'] if st else None,
                    f'Product update draft {key} not previewed',
                    md=f":warning: **Product update draft {key} can't be previewed:** {problem}",
                )
                log('draft refused', key, problem)
            continue
        if not st:
            head = slack.post(
                dm,
                None,
                f'Product update draft: {meta.get("title", key)}',
                md=f'**:newspaper: Product update draft ready:** {meta.get("title", key)}',
                note='The preview below is exactly what will be posted.',
            )
            st = state['drafts'][key] = {'revision': 0, 'dm': dm, 'thread': head, 'buttons': None}
            st['status'] = DRAFT.first('pending')
        else:
            slack.post(dm, st['thread'], 'Revised draft', note=f':pencil2: Revision {rev}')
        _send(dm, text_md, images, st['thread'])
        if old := st.get('buttons'):
            slack.update(
                dm,
                old,
                'Replaced by a newer revision',
                note=f'Revision {st["revision"]}: replaced by revision {rev}.',
            )
        r = slack.app.client.chat_postMessage(
            channel=dm,
            thread_ts=st['thread'],
            text='Post or discard this draft',
            blocks=_buttons(key, rev, st, has_video(images)),
            reply_broadcast=bool(st['revision']),
        )
        st.update({'revision': rev, 'buttons': r['ts'], 'mtime': mtime})
        log('draft preview', key, 'revision', rev)
        save()


def for_thread(ch: str, tts: str) -> tuple[str | None, Draft | None]:
    for key, st in state['drafts'].items():
        if st['dm'] == ch and st['thread'] == tts:
            return key, st
    return None, None


def _draft_has_video(key: str) -> bool:
    d = os.path.join(DRAFTS, key)
    try:
        with open(os.path.join(d, 'ready.json')) as f:
            return has_video(_files(d, json.load(f))[1])
    except (OSError, ValueError):
        return False


def revise(key: str, st: Draft, text: str, ts: str) -> None:
    """Owner feedback on a draft -> a T3 chat that rewrites the draft files."""
    if DRAFT.is_(st.get('status'), 'discarded'):
        slack.post(st['dm'], st['thread'], 'Discarded', note='This draft was discarded, so there is nothing to change.')
        return
    slack.react(st['dm'], ts, 'eyes')
    tid, err = t3.start_thread(
        projects.route('draft')['project'],
        f'Revise product update {key}',
        prompts.revise_draft(
            AGENT_DRAFTS, key, slack.name(OWNER), slack.readable(text), st['revision'] + 1, _draft_has_video(key)
        ),
    )
    slack.react(st['dm'], ts, 'eyes', remove=True)
    if tid:
        slack.react(st['dm'], ts, 'pencil2')
        if DRAFT.is_(st.get('status'), 'posted'):  # a pending or previewed draft just gets its next revision
            st['status'] = DRAFT.to(st.get('status'), 'revising')
        save()
    else:
        slack.post(st['dm'], st['thread'], f":warning: Couldn't start the revision: {err}")


def _finish(ack: Ack, body: Json, posting: bool) -> None:
    ack()
    if body['user']['id'] != OWNER:
        return
    key = body['actions'][0]['value']
    with lock:
        st = state['drafts'].get(key)
        if not st or not DRAFT.is_(st.get('status'), 'pending', 'editing'):
            return
        btn = body['container']['message_ts']
        channel = publish_channel()
        if DRAFT.is_(st.get('status'), 'editing'):
            _finish_edit(st, key, btn, posting)
            return
        if posting and not channel:
            slack.post(
                st['dm'], st['thread'], ':warning: No product updates channel yet: set one on the hub, then tap again.'
            )
            return
        if posting:
            d = os.path.join(DRAFTS, key)
            with open(os.path.join(d, 'ready.json')) as f:
                text_md, images = _files(d, json.load(f))
            try:
                st['posted'] = _send(channel, text_md, images)
            except Exception as e:
                slack.post(
                    st['dm'], st['thread'], f':warning: Posting failed: {str(e)[:300]}. Is {NAME} in <#{channel}>?'
                )
                return
            st['status'] = DRAFT.to(st.get('status'), 'posted')
            slack.update(
                st['dm'], btn, 'Posted', note=f':white_check_mark: Posted to <#{channel}> (revision {st["revision"]}).'
            )
        else:
            st['status'] = DRAFT.to(st.get('status'), 'discarded')
            slack.update(
                st['dm'],
                btn,
                'Discarded',
                note=f':wastebasket: Discarded (revision {st["revision"]}). Nothing was posted.',
            )
        log('draft', key, st['status'])
        where = '#' + (slack.channel_name(channel) or channel)
        COMP.event(
            'sent' if posting else 'skipped',
            'Product update ' + (f'posted to {where}' if posting else 'discarded'),
            to=where if posting else None,
            detail=f'revision {st["revision"]}',
        )
        save()


def _finish_edit(st: Draft, key: str, btn: str, updating: bool) -> None:
    if not updating:
        st['status'] = DRAFT.to(st.get('status'), 'posted')
        slack.update(
            st['dm'], btn, 'Kept', note=f':no_entry_sign: Kept the post as it was (revision {st["revision"]}).'
        )
        save()
        return
    text_md, _ = _files(os.path.join(DRAFTS, key), {'images': []})
    try:
        channel = _edit(st, text_md)
    except Exception as e:  # still editing: the owner can tap again
        slack.post(st['dm'], st['thread'], 'Edit failed', note=f':warning: Updating the post failed: {str(e)[:300]}')
        return
    st['status'] = DRAFT.to(st.get('status'), 'posted')
    slack.update(
        st['dm'], btn, 'Updated', note=f':pencil2: Updated the post in <#{channel}> (revision {st["revision"]}).'
    )
    log('draft', key, 'edited')
    where = '#' + (slack.channel_name(channel) or channel)
    COMP.event('sent', f'Product update edited in {where}', to=where, detail=f'revision {st["revision"]}')
    save()


slack.app.action('draft_post')(lambda ack, body: _finish(ack, body, True))
slack.app.action('draft_discard')(lambda ack, body: _finish(ack, body, False))
