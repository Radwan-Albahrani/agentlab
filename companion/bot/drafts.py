"""Product-update drafts: an agent (e.g. the Sunday T3 scheduled task) writes one into
/workspace/.companion/product-updates/<id>/:
  update.md   the message, standard markdown        *.png/*.jpg   screenshots, in order
  ready.json  written LAST: {"title": "...", "images": ["a.png", ...], "revision": 1}
The companion DMs the owner the preview exactly as it will be posted, with Post / Discard buttons. Replies in that DM
thread start a revision chat; a newer ready.json brings a fresh preview. Nothing reaches the channel without
the owner's tap. The channel is a setting on the hub.
After posting, replies in the same DM thread still revise it: the new preview's button edits the posted message in
place (its text; the screenshots stay as posted) instead of posting again."""

import json
import os
import re
import time

from . import prompts, slack, t3
from .config import AGENT_FILES, COMP, DEFAULT_PROJECT, FILES, NAME, OWNER, log, publish_channel
from .state import lock, save, state
from .text import first_sentence, to_slack

DRAFTS = os.path.join(FILES, 'product-updates')
AGENT_DRAFTS = f'{AGENT_FILES}/product-updates'
IMAGE_REF = re.compile(r'^[ \t]*!\[[^\]]*\]\([^)]*\)[ \t]*\n?', re.M)


def _files(d, meta):
    imgs = meta.get('images') or sorted(
        f for f in os.listdir(d) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))
    )
    with open(os.path.join(d, 'update.md'), encoding='utf-8') as f:
        text = f.read()
    text = re.sub(r'\n{3,}', '\n\n', IMAGE_REF.sub('', text)).strip()  # the screenshots go up as files instead
    return text, [os.path.join(d, f) for f in imgs if os.path.isfile(os.path.join(d, f))]


def _send(channel, text_md, images, thread_ts=None):
    """Post the update the way it will look in the channel: text plus screenshots in one message.
    Returns where it landed, for a later edit."""
    if images:
        since = time.time() - 5
        slack.app.client.files_upload_v2(
            channel=channel,
            thread_ts=thread_ts,
            initial_comment=to_slack(text_md, 3900),
            file_uploads=[{'file': p, 'filename': os.path.basename(p)} for p in images],
        )
        return {'channel': channel, 'ts': None if thread_ts else _find_upload(channel, since), 'files': True}
    return {'channel': channel, 'ts': slack.post(channel, thread_ts, first_sentence(text_md, 300), md=text_md)}


def _find_upload(channel, since, tries=5):
    """An upload doesn't return its message: The companion's newest message with files in the channel since `since`."""
    for i in range(tries):
        msgs = slack.app.client.conversations_history(channel=channel, oldest=f'{since:.6f}', limit=50)['messages']
        for m in msgs:  # newest first
            if m.get('files') and m.get('user') == slack.bot_user():
                return m['ts']
        if i < tries - 1:
            time.sleep(1)  # Slack shares the files a moment after the upload returns
    return None


def _edit(st, text_md):
    """The posted message, rewritten in place. Posts from before the companion kept their place are looked up once, from
    when the draft's DM thread began (always before the post; a revision's mtime is after it)."""
    p = st.get('posted') or {'channel': publish_channel(), 'ts': None, 'files': True}
    if not p['ts']:
        p['ts'] = _find_upload(p['channel'], float(st['thread']), tries=1)
        if not p['ts']:
            raise RuntimeError(f"couldn't find the posted message in <#{p['channel']}>")
        st['posted'] = p
    if p.get('files'):
        slack.app.client.chat_update(channel=p['channel'], ts=p['ts'], text=to_slack(text_md, 3900))
    else:
        slack.update(p['channel'], p['ts'], first_sentence(text_md, 300), md=text_md)
    return p['channel']


def _buttons(key, rev, st):
    if st['status'] == 'editing':
        ch = (st.get('posted') or {}).get('channel') or publish_channel()
        head, go, stop = f'*Edit of the post in <#{ch}>* · revision {rev}', 'Update the post', 'Keep it as it is'
        foot = 'Updates the text in place; the screenshots stay as posted. Reply here to change something.'
    else:
        head, go, stop = f'*Draft for <#{publish_channel()}>* · revision {rev}', 'Post to the channel', 'Discard'
        foot = 'Reply in this thread to change something.'
    return [
        {'type': 'section', 'text': {'type': 'mrkdwn', 'text': head}},
        slack.buttons(('draft_post', go, key, 'primary'), ('draft_discard', stop, key, None)),
        {'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': foot}]},
    ]


def tick():
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
            continue  # not finished yet
        rev = int(meta.get('revision', 1))
        st = state['drafts'].get(key)
        if st and mtime <= st.get('mtime', 0):
            continue  # nothing new written
        if st and st['status'] == 'posted' and st.get('revising'):
            st['status'] = 'editing'  # the owner asked to change what's already in the channel
        elif st and st['status'] not in ('pending', 'editing'):  # a new run into a posted/discarded folder
            state['drafts'].pop(key)  # (same day): a fresh draft, new DM thread
            st = None
        if st and rev <= st['revision']:
            rev = st['revision'] + 1  # rewritten without bumping: still a revision
        text_md, images = _files(d, meta)
        dm = slack.dm_owner()
        if not st:  # first preview: its own DM thread
            head = slack.post(
                dm,
                None,
                f'Product update draft: {meta.get("title", key)}',
                md=f'**:newspaper: Product update draft ready:** {meta.get("title", key)}',
                note='The preview below is exactly what will be posted.',
            )
            st = state['drafts'][key] = {'status': 'pending', 'revision': 0, 'dm': dm, 'thread': head, 'buttons': None}
        else:
            slack.post(dm, st['thread'], 'Revised draft', note=f':pencil2: Revision {rev}')
        _send(dm, text_md, images, st['thread'])
        if st.get('buttons'):  # older revision's buttons: retire them
            slack.update(
                dm,
                st['buttons'],
                'Replaced by a newer revision',
                note=f'Revision {st["revision"]}: replaced by revision {rev}.',
            )
        r = slack.app.client.chat_postMessage(
            channel=dm,
            thread_ts=st['thread'],
            text='Post or discard this draft',
            blocks=_buttons(key, rev, st),
            reply_broadcast=bool(st['revision']),
        )
        st.update(revision=rev, buttons=r['ts'], revising=False, mtime=mtime)
        log('draft preview', key, 'revision', rev)
        save()


def for_thread(ch, tts):
    for key, st in state['drafts'].items():
        if st['dm'] == ch and st['thread'] == tts:
            return key, st
    return None, None


def revise(key, st, text, ts):
    """Owner feedback on a draft -> a T3 chat that rewrites the draft files (The companion previews the result)."""
    if st['status'] == 'discarded':
        slack.post(st['dm'], st['thread'], 'Discarded', note='This draft was discarded, so there is nothing to change.')
        return
    slack.react(st['dm'], ts, 'eyes')
    tid, err = t3.start_thread(
        DEFAULT_PROJECT,
        f'Revise product update {key}',
        prompts.revise_draft(AGENT_DRAFTS, key, slack.name(OWNER), slack.readable(text), st['revision'] + 1),
    )
    slack.react(st['dm'], ts, 'eyes', remove=True)
    if tid:
        slack.react(st['dm'], ts, 'pencil2')
        st['revising'] = True
        save()
    else:
        slack.post(st['dm'], st['thread'], f":warning: Couldn't start the revision: {err}")


def _finish(ack, body, posting):
    ack()
    if body['user']['id'] != OWNER:
        return
    key = body['actions'][0]['value']
    with lock:
        st = state['drafts'].get(key)
        if not st or st['status'] not in ('pending', 'editing'):
            return
        btn = body['container']['message_ts']
        channel = publish_channel()
        if st['status'] == 'editing':
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
            st['status'] = 'posted'
            slack.update(
                st['dm'], btn, 'Posted', note=f':white_check_mark: Posted to <#{channel}> (revision {st["revision"]}).'
            )
        else:
            st['status'] = 'discarded'
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


def _finish_edit(st, key, btn, updating):
    st['status'] = 'posted'
    if not updating:
        slack.update(
            st['dm'], btn, 'Kept', note=f':no_entry_sign: Kept the post as it was (revision {st["revision"]}).'
        )
        save()
        return
    text_md, _ = _files(os.path.join(DRAFTS, key), {'images': []})
    try:
        channel = _edit(st, text_md)
    except Exception as e:
        st['status'] = 'editing'
        slack.post(st['dm'], st['thread'], 'Edit failed', note=f':warning: Updating the post failed: {str(e)[:300]}')
        return
    slack.update(
        st['dm'], btn, 'Updated', note=f':pencil2: Updated the post in <#{channel}> (revision {st["revision"]}).'
    )
    log('draft', key, 'edited')
    where = '#' + (slack.channel_name(channel) or channel)
    COMP.event('sent', f'Product update edited in {where}', to=where, detail=f'revision {st["revision"]}')
    save()


slack.app.action('draft_post')(lambda ack, body: _finish(ack, body, True))
slack.app.action('draft_discard')(lambda ack, body: _finish(ack, body, False))
