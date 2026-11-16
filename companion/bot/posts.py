"""The agent's post.json: a message or poll for a channel, DMs to people, or an edit of a message it sent before;
previewed for the owner unless review is off."""

import time
from datetime import datetime

from . import errands, polls, slack
from .config import COMP, NAME, OWNER, log
from .state import key_of, save
from .text import clock, first_sentence, quote

MAX_OPTIONS = 10
MAX_PEOPLE = 10


def in_channel(task):
    return not task['channel'].startswith('D')


def _direct(p):
    names = p['to'] if isinstance(p['to'], list) else [p['to']]
    if p.get('poll'):
        return None, 'a poll goes to a channel, not to DMs'
    if len(names) > MAX_PEOPLE:
        return None, f'that is more than {MAX_PEOPLE} people; post it in a channel instead'
    ids = []
    for n in names:
        uid, problem = slack.find_user(str(n))
        if problem:
            return None, problem
        ids.append(uid)
    text = str(p.get('text') or '').strip()[:3000]
    return ({'to': list(dict.fromkeys(ids)), 'text': text}, '') if text else (None, 'there is nothing to send')


def where(post, md=False):
    """'#general', or 'Ali by DM' ('<@U…> by DM' in markdown)."""
    if post.get('edit'):
        return post['where']
    if post.get('to'):
        people = [f'<@{u}>' if md else slack.name(u) for u in post['to']]
        return ', '.join(people) + ' by DM'
    if post.get('thread'):
        return 'the thread'
    return f'<#{post["channel"]}>' if md else '#' + (slack.channel_name(post['channel']) or post['channel'])


def parse(p, default=''):
    """(post, problem): a clean post, or why it can't be used; no channel means `default`."""
    if p.get('to'):
        return _direct(p)
    known = slack.channels()
    names = {c['name']: c['id'] for c in known}
    ch = str(p.get('channel') or '').strip().lstrip('#') or default
    ch = names.get(ch, ch)
    if not ch:
        return None, 'it names no channel'
    if ch not in {c['id'] for c in known if c['member']}:
        return None, f'I am not in <#{ch}>. Invite me there with `/invite @{NAME}`, then reply here to try again'
    post = {'channel': ch, 'text': str(p.get('text') or '').strip()[:3000]}
    if p.get('poll'):
        poll, problem = _poll(p['poll'])
        if problem:
            return None, problem
        post['poll'] = poll
    elif not post['text']:
        return None, 'there is nothing to post'
    return post, ''


def _poll(p):
    question = str(p.get('question') or '').strip()[:300]
    options = list(dict.fromkeys(str(o).strip()[:75] for o in p.get('options') or [] if str(o).strip()))
    if not question or not 2 <= len(options) <= MAX_OPTIONS:
        return None, f'a poll needs a question and 2 to {MAX_OPTIONS} different options'
    try:
        closes = datetime.fromisoformat(str(p.get('closes'))).timestamp()
    except ValueError:
        return None, 'the poll\'s "closes" is not an ISO 8601 time'
    if not 0 < closes - datetime.now().timestamp() < 30 * 86400:
        return None, 'the poll must close in the future, within 30 days'
    return {'question': question, 'options': options, 'closes': closes, 'multiple': bool(p.get('multiple'))}, ''


def _edit(task, p):
    """(post, problem): an edit of a message this task sent before (post.json with "edit": its id)."""
    sent = {m['id']: m for m in task.get('sent') or []}
    m = sent.get(str(p['edit']).strip().lstrip('#'))
    if not m:
        known = ', '.join(f'{i} ({s["where"]})' for i, s in sent.items()) or 'none'
        return None, f'"edit" names no message this task sent (its messages: {known})'
    text = str(p.get('text') or '').strip()[:3000]
    if not text:
        return None, 'the edit has no new text'
    return {'edit': m['id'], 'where': m['where'], 'msgs': m['msgs'], 'channel': m['msgs'][0][0], 'text': text}, ''


def sent_list(task):
    """The messages this task posted, for the agent to edit: '- 1: in #general: "Post-mortem is up…"'."""
    return '\n'.join(f'- {m["id"]}: {m["where"]}: "{first_sentence(m["text"], 80)}"' for m in task.get('sent') or [])


def preview_md(post):
    if post.get('edit'):
        return f'**Edit your message {post["where"]} to:**\n' + quote(post['text'])
    md = f'**To {where(post, md=True)}:**' + ('\n' + quote(post['text']) if post['text'] else '')
    if post.get('poll'):
        md += '\n\n' + polls.describe(post['poll'])
    return md


def offer(task, p):
    """post.json -> a preview to approve, or sent at once."""
    ch, tts = task['channel'], task['thread_ts']
    post, problem = _edit(task, p) if p.get('edit') else parse(p, ch if in_channel(task) else '')
    if problem:
        slack.post(ch, tts, 'Could not use the post', md=f':warning: The agent prepared a post, but {problem}.')
        return
    asked_here = in_channel(task) and post.get('channel') == ch
    if asked_here and not post.get('poll') and not p.get('new_message') and not post.get('edit'):
        post['thread'] = tts
    if asked_here or not task.get('review', True):
        send(task, post)
        return
    k = key_of(task)
    old = task.pop('post_draft', None)
    if old:
        line = ':pencil2: Replaced by the version below'
        slack.app.client.chat_update(
            channel=old.get('at') or ch, ts=old['ts'], text=line, blocks=slack.blocks(old['md'], line)
        )
    guest = task.get('guest')
    md = ':outbox_tray: ' + preview_md(post)
    if guest:
        link = slack.permalink(ch, tts)
        md += f'\n\nAsked by **{slack.name(guest)}**' + (f' · <{link}|open their thread>' if link else '')
        slack.note_only(ch, tts, f':hourglass_flowing_sand: Waiting for {slack.name(OWNER)} to approve sending it')
    at, at_thread = errands.approver(task)
    ts = slack.app.client.chat_postMessage(
        channel=at,
        thread_ts=at_thread,
        text='Edit this?' if post.get('edit') else 'Post this?',
        blocks=[
            *slack.blocks(
                md,
                ('Nothing has been changed yet.' if post.get('edit') else 'Nothing has been posted yet.')
                + ('' if guest else ' Reply here to change it.'),
            ),
            slack.buttons(
                (
                    'post_send',
                    'Edit it' if post.get('edit') else 'Send it' if post.get('to') else 'Post it',
                    k,
                    'primary',
                ),
                (
                    'post_skip',
                    "Don't edit" if post.get('edit') else "Don't send" if post.get('to') else "Don't post",
                    k,
                    None,
                ),
            ),
        ],
    )['ts']
    task['post_draft'] = {**post, 'ts': ts, 'md': md, 'at': at}
    what = f'an edit of your message {post["where"]}' if post.get('edit') else f'a message for {where(post)}'
    COMP.event('approval', f'Asked you to check {what}', task=k)
    save()


def decide(task, k, send_it):
    d = task.pop('post_draft', None)
    if not d:
        return
    line = (
        (':white_check_mark: Editing' if send_it else ':no_entry_sign: Not edited')
        if d.get('edit')
        else (':white_check_mark: Posting' if send_it else ':no_entry_sign: Not posted')
    ) + f' at {clock(time.time())}'
    slack.app.client.chat_update(
        channel=d.get('at') or task['channel'], ts=d['ts'], text=line, blocks=slack.blocks(d['md'], line)
    )
    if send_it:
        send(task, {f: d[f] for f in ('channel', 'to', 'text', 'poll', 'edit', 'where', 'msgs') if f in d})
    else:
        if task.get('guest'):
            slack.note_only(
                task['channel'], task['thread_ts'], f':no_entry_sign: {slack.name(OWNER)} chose not to send it'
            )
        COMP.event('skipped', 'You chose not to post it', task=k)
    save()


def edit(task, post):
    """Change a message this task sent, everywhere it went."""
    ch, tts, k = task['channel'], task['thread_ts'], key_of(task)
    try:
        for at, ts in post['msgs']:
            slack.app.client.chat_update(
                channel=at, ts=ts, text=first_sentence(post['text'], 200), blocks=slack.blocks(post['text'])
            )
    except Exception as e:
        log('edit failed:', e)
        slack.post(ch, tts, 'Editing failed', md=f":warning: Couldn't edit the message {post['where']}: {str(e)[:200]}")
        return
    m = next(m for m in task['sent'] if m['id'] == post['edit'])
    m['text'] = post['text']
    at, ts = post['msgs'][0]
    link = None if at.startswith('D') else slack.permalink(at, ts)
    slack.note_only(ch, tts, f':pencil2: Edited the message {post["where"]}' + (f' · <{link}|open>' if link else ''))
    COMP.event('sent', f'Message edited {post["where"]}', task=k, to=post['where'], detail=post['text'])
    save()


def send(task, post):
    if post.get('edit'):
        edit(task, post)
        return
    ch, tts, k = task['channel'], task['thread_ts'], key_of(task)
    dest = where(post)
    at = []
    try:
        if post.get('poll'):
            poll = polls.start(post, k)
            task['poll'], ts = poll['id'], poll['ts']
        else:
            for to in post.get('to') or [post['channel']]:
                dest_id = slack.app.client.conversations_open(users=to)['channel']['id'] if post.get('to') else to
                ts = slack.app.client.chat_postMessage(
                    channel=dest_id,
                    thread_ts=post.get('thread'),
                    text=first_sentence(post['text'], 200),
                    blocks=slack.blocks(post['text']),
                    unfurl_links=False,
                )['ts']
                at.append([dest_id, ts])
    except Exception as e:
        log('post failed:', e)
        slack.post(ch, tts, 'Posting failed', md=f":warning: Couldn't send it to {dest}: {str(e)[:200]}")
        return
    link = None if post.get('to') else slack.permalink(post['channel'], ts)
    what = 'Poll' if post.get('poll') else 'Message'
    sent = f'sent to {dest}' if post.get('to') else f'posted in {dest}'
    note = f':white_check_mark: {what} {sent}' + (f' · <{link}|open>' if link else '')
    if post.get('poll'):
        note += f' · closes {clock(post["poll"]["closes"])}'
    if not post.get('thread'):
        slack.note_only(ch, tts, note)
    if post.get('poll'):  # close button goes to the owner's DM only
        dm, dm_thread = (slack.dm_owner(), None) if in_channel(task) else (ch, tts)
        slack.app.client.chat_postMessage(
            channel=dm,
            thread_ts=dm_thread,
            text=f'Poll in {dest}',
            blocks=[
                *slack.blocks(
                    None, f':bar_chart: {post["poll"]["question"]} · in {dest}' + (f' · <{link}|open>' if link else '')
                ),
                slack.buttons(('poll_close', 'Close the poll now', task['poll'], None)),
            ],
        )
    task.update(closed=note, posted=True)
    if at:
        sent = task.setdefault('sent', [])
        sent.append(
            {
                'id': str(len(sent) + 1),
                'where': f'to {dest}' if post.get('to') else f'in {dest}',
                'msgs': at,
                'text': post['text'],
            }
        )
    COMP.event(
        'sent',
        f'{what} {sent}',
        task=k,
        to=dest,
        detail=post['poll']['question'] if post.get('poll') else post['text'],
    )
    save()


slack.app.action('post_send')(errands.owner_action(lambda t, k: decide(t, k, True)))
slack.app.action('post_skip')(errands.owner_action(lambda t, k: decide(t, k, False)))
