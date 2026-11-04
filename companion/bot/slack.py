"""Slack clients (bot, and the owner's read-only user token), message layout and transcripts for the agent."""

import contextlib
import os
import re
import time
import urllib.request
from datetime import datetime

from slack_bolt import App

from .config import AGENT_FILES, FILES, OWNER, log, secret
from .text import to_slack

app = App(token=secret('bot-token.txt'), token_verification_enabled=False)  # main.run checks it
try:
    from slack_sdk import WebClient

    USER = WebClient(token=secret('user-token.txt'))  # read-only, as the owner
except Exception:
    USER = None
WORKSPACE = ''  # https://<workspace>.slack.com/, set at start
_people = {'at': 0.0, 'list': [], 'by_id': {}}  # cached workspace directory
_others = {}  # id -> users_info record for people missing from _people
_bot = []


def _refresh_people():
    found, cursor = [], None
    try:
        while True:
            res = app.client.users_list(limit=500, cursor=cursor)
            found += res['members']
            cursor = (res.get('response_metadata') or {}).get('next_cursor')
            if not cursor:
                break
    except Exception as e:
        log('people list unavailable:', str(e)[:80])
        found = None
    _people['at'] = time.time()
    if found is not None:
        _people['by_id'] = {u['id']: u for u in found}
        _people['list'] = [u for u in found if not u.get('deleted') and not u.get('is_bot')]


def people():
    """The workspace's active people (no bots), cached ten minutes."""
    if time.time() - _people['at'] > 600:
        _refresh_people()
    return _people['list']


def _member(uid):
    people()
    m = _people['by_id'].get(uid)
    if m is None:
        if uid not in _others:
            try:
                _others[uid] = app.client.users_info(user=uid)['user']
            except Exception:
                _others[uid] = {'id': uid}
        m = _others[uid]
    return m


def member_name(u):
    return u.get('profile', {}).get('display_name') or u.get('real_name') or u.get('name') or u['id']


def name(uid):
    return member_name(_member(uid))


def avatar(uid):
    """48 px profile picture URL, or ''."""
    return _member(uid).get('profile', {}).get('image_48') or ''


def find_user(text):
    """(user id, '') for a name, @mention or id; (None, why) when no one or several match."""
    text = text.strip()
    m = re.fullmatch(r'<?@?([UW][A-Z0-9]{6,})>?', text)
    if m:
        return m.group(1), ''
    if text in _people['by_id']:
        return text, ''
    want = text.strip().lstrip('@').casefold()

    def names(u):
        p = u.get('profile', {})
        return {
            x.casefold() for x in (u.get('name'), u.get('real_name'), p.get('display_name'), p.get('real_name')) if x
        }

    everyone = people()
    hits = [u for u in everyone if want in names(u)] or [
        u for u in everyone if want and any(want in n for n in names(u))
    ]
    if len(hits) == 1:
        return hits[0]['id'], ''
    if not hits:
        return None, f'Nobody in Slack is called "{text}".'
    return (
        None,
        f'"{text}" matches {len(hits)} people ({", ".join(name(u["id"]) for u in hits[:5])}); be more specific.',
    )


def bot_user():
    if not _bot:
        _bot.append(app.client.auth_test()['user_id'])
    return _bot[0]


def dm_owner():
    return app.client.conversations_open(users=OWNER)['channel']['id']


def channel_name(channel):
    """A channel id's name; '' for DMs or without the read scopes."""
    if channel[:1] not in ('C', 'G'):
        return ''
    try:
        return app.client.conversations_info(channel=channel)['channel'].get('name', '')
    except Exception as e:
        log('channel name unavailable:', str(e)[:80])
        return ''


_channels = {'at': 0.0, 'list': []}


def channels():
    """[{id, name, member}] of public channels and private ones the bot is in (member: bot can post), cached."""
    if time.time() - _channels['at'] > 300:
        found, cursor = [], None
        try:
            while True:
                res = app.client.conversations_list(
                    types='public_channel,private_channel', exclude_archived=True, limit=1000, cursor=cursor
                )
                found += [
                    {'id': c['id'], 'name': c['name'], 'member': bool(c.get('is_member'))} for c in res['channels']
                ]
                cursor = (res.get('response_metadata') or {}).get('next_cursor')
                if not cursor:
                    break
            _channels['list'] = sorted(found, key=lambda c: c['name'])
        except Exception as e:
            log('channel list unavailable:', str(e)[:80])
        _channels['at'] = time.time()
    return _channels['list']


def bot_in(channel):
    try:
        return bool(app.client.conversations_info(channel=channel)['channel'].get('is_member'))
    except Exception:
        return False


def permalink(channel, ts, client=None):
    try:
        return (client or app.client).chat_getPermalink(channel=channel, message_ts=ts)['permalink']
    except Exception:
        return ''


def link(channel, ts):
    """A message link built without an API call."""
    return f'{WORKSPACE}archives/{channel}/p{ts.replace(".", "")}' if WORKSPACE and channel and ts else ''


def readable(text):
    """Slack markup -> plain text: <@U1> -> @name, <url|label> -> label (url)."""
    text = re.sub(r'<@([A-Z0-9]+)>', lambda m: '@' + name(m.group(1)), text or '')
    text = re.sub(r'<#[A-Z0-9]+\|([^>]+)>', r'#\1', text)
    text = re.sub(r'<(https?://[^|>]+)\|([^>]+)>', r'\2 (\1)', text)
    text = re.sub(r'<(https?://[^>]+)>', r'\1', text)
    return text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')


def blocks(md=None, note=None, legacy=False):
    """Block Kit: `md` as a markdown block (mrkdwn sections if `legacy`), `note` as a grey context line."""
    b = []
    if md:
        if legacy:
            t = to_slack(md, 11000)
            b += [
                {'type': 'section', 'text': {'type': 'mrkdwn', 'text': t[i : i + 2900]}} for i in range(0, len(t), 2900)
            ]
        else:
            b.append({'type': 'markdown', 'text': md[:11500]})
    if note:
        b.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': note[:2900]}]})
    return b or None


def buttons(*items):
    """An actions block: items are (action_id, label, value, style or None)."""
    return {
        'type': 'actions',
        'elements': [
            {
                'type': 'button',
                'action_id': a,
                'value': v,
                'text': {'type': 'plain_text', 'text': label[:75]},
                **({'style': style} if style else {}),
            }
            for a, label, v, style in items
        ],
    }


def _send(call, md, note, **kw):
    for legacy in (False, True):
        try:
            return call(blocks=blocks(md, note, legacy), **kw)
        except Exception as e:
            if legacy or 'invalid_blocks' not in str(e):
                log(f'{call.__name__} failed:', e)
                break
    return None


def post(channel, thread_ts, text, md=None, note=None):
    """text: notification/fallback text; md and note: what the message shows."""
    r = _send(
        app.client.chat_postMessage,
        md,
        note,
        channel=channel,
        thread_ts=thread_ts,
        text=text[:3000],
        unfurl_links=False,
        unfurl_media=False,
    )
    return r['ts'] if r else None


def update(channel, ts, text, md=None, note=None):
    _send(app.client.chat_update, md, note, channel=channel, ts=ts, text=text[:3000])


def note_only(channel, thread_ts, line):
    """Post one small grey line."""
    return post(channel, thread_ts, re.sub(r':[a-z_]+:\s*', '', line), note=line)


def react(channel, ts, emoji, remove=False):
    with contextlib.suppress(Exception):
        (app.client.reactions_remove if remove else app.client.reactions_add)(channel=channel, timestamp=ts, name=emoji)


def upload(channel, thread_ts, paths, comment=None):
    return app.client.files_upload_v2(
        channel=channel,
        thread_ts=thread_ts,
        initial_comment=comment,
        file_uploads=[{'file': p, 'filename': os.path.basename(p)} for p in paths],
    )


def download(files, folder):
    """Download Slack files into <folder>; returns the paths as the agent sees them."""
    out = []
    os.makedirs(os.path.join(FILES, folder), exist_ok=True)
    for f in files or []:
        url = f.get('url_private_download') or f.get('url_private')
        if not url:
            continue
        fname = re.sub(r'[^\w.\-]+', '_', f.get('name') or f.get('id', 'file'))[:80]
        try:
            req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + app.client.token})
            with urllib.request.urlopen(req, timeout=60) as r, open(os.path.join(FILES, folder, fname), 'wb') as w:
                w.write(r.read())
            os.chmod(os.path.join(FILES, folder, fname), 0o644)
            out.append(f'{AGENT_FILES}/{folder}/{fname}')
        except Exception as e:
            log('file download failed:', fname, e)
    return out


def transcript(msgs, folder=None):
    """Messages -> ('[Oct 28 12:30] Name: text' lines, downloaded file paths), skipping the bot's own posts."""
    me, lines, files = bot_user(), [], []
    for m in msgs:
        if m.get('user') == me:
            continue
        who = (m.get('bot_profile') or {}).get('name') or name(m.get('user', '?'))
        if m.get('bot_id'):
            who += ' (app)'
        text = m.get('text') or ''
        for a in m.get('attachments') or []:
            text += '\n' + (a.get('text') or a.get('fallback') or '')
        when = datetime.fromtimestamp(float(m['ts'])).strftime('%b %d %H:%M')
        lines.append(f'[{when}] {who}: {readable(text.strip())}')
        got = download(m.get('files'), folder) if folder else []
        if got:
            lines.append('    attached: ' + ', '.join(os.path.basename(g) for g in got))
        files += got
    return lines, files


def thread_messages(channel, thread_ts, trigger_ts):
    """The whole thread, or recent channel history for a top-level tag."""
    try:
        if thread_ts != trigger_ts:
            return app.client.conversations_replies(channel=channel, ts=thread_ts, limit=200)['messages']
        return list(
            reversed(
                app.client.conversations_history(channel=channel, latest=trigger_ts, inclusive=True, limit=12)[
                    'messages'
                ]
            )
        )
    except Exception as e:
        log('context failed:', e)
        return []
