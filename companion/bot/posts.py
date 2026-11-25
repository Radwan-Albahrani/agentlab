"""Ledger messages for a channel or people (with a poll, maybe) and edits of messages sent before: previewed for the
owner unless they go to the task's own channel or review is off. Each preview card belongs to one ledger item."""

from datetime import datetime

from . import attachments, cases, errands, ledger, machine, polls, slack
from .config import COMP, NAME, log
from .shapes import Item, Json, PollSpec, Post, Task
from .state import key_of
from .text import first_sentence, quote
from .when import say

MAX_OPTIONS = 10
MAX_PEOPLE = 10


def in_channel(task: Task) -> bool:
    return not task['channel'].startswith('D')


def _direct(names: list[str], text: str, poll: Json | None, files: bool = False) -> tuple[Post | None, str]:
    """files: it carries files, so it may have no text."""
    if poll:
        return None, 'a poll goes to a channel, not to DMs'
    if len(names) > MAX_PEOPLE:
        return None, f'that is more than {MAX_PEOPLE} people; post it in a channel instead'
    ids: list[str] = []
    for n in names:
        uid, problem = slack.find_user(n)
        if problem or uid is None:
            return None, problem or f'no one is called {n}'
        ids.append(uid)
    text = text.strip()[:3000]
    if not text and not files:
        return None, 'there is nothing to send'
    return {'to': list(dict.fromkeys(ids)), 'text': text}, ''


def where(post: Post, md: bool = False) -> str:
    """'#general', or 'Ali by DM' ('<@U…> by DM' in markdown)."""
    if 'edit' in post:
        return post['where']
    if post.get('to'):
        people = [f'<@{u}>' if md else slack.name(u) for u in post['to']]
        return ', '.join(people) + ' by DM'
    if post.get('thread'):
        return 'the thread'
    return f'<#{post["channel"]}>' if md else '#' + (slack.channel_name(post['channel']) or post['channel'])


def parse(p: Json, default: str = '') -> tuple[Post | None, str]:
    """(post, problem): the agent's message (its own JSON) as a clean post, or why it can't be used; no channel
    means `default`."""
    to = p.get('to')
    if to:
        return _direct(
            [str(n) for n in to] if isinstance(to, list) else [str(to)], str(p.get('text') or ''), p.get('poll')
        )
    return _to_channel(str(p.get('channel') or ''), str(p.get('text') or ''), p.get('poll'), default)


def _to_channel(
    channel: str, text: str, raw_poll: Json | None, default: str = '', files: bool = False
) -> tuple[Post | None, str]:
    known = slack.channels()
    names = {c['name']: c['id'] for c in known}
    ch = channel.strip().lstrip('#') or default
    ch = names.get(ch, ch)
    if not ch:
        return None, 'it names no channel'
    if ch not in {c['id'] for c in known if c['member']}:
        return None, f'I am not in <#{ch}>. Invite me there with `/invite @{NAME}`, then reply here to try again'
    post: Post = {'channel': ch, 'text': text.strip()[:3000]}
    if raw_poll and files:
        return None, "a poll can't carry files: send them in a message of their own"
    if raw_poll:
        poll, problem = _poll(raw_poll)
        if poll is None:
            return None, problem
        post['poll'] = poll
    elif not post['text'] and not files:
        return None, 'there is nothing to post'
    return post, ''


def _poll(p: Json) -> tuple[PollSpec | None, str]:
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


def _target(task: Task, it: Item, files: bool) -> tuple[Post | None, str]:
    """(post, problem) for a ledger message to a channel or people (files: it carries some), or an edit."""
    if it['kind'] == 'edit':
        return _edit(task, it)
    if it['to'] == 'people':
        raw = it.get('raw_to')
        names = [str(n) for n in raw] if isinstance(raw, list) else [it['label']]
        return _direct(names, it['text'], it.get('poll'), files)
    ch = it['label'].lstrip('#')
    if ch.startswith('<#'):
        ch = ch[2:-1]
    return _to_channel(ch, it['text'], it.get('poll'), files=files)


def _sent_messages(task: Task) -> dict[str, Item]:
    """{id: item}: ledger messages that went to a channel or people (where they landed is in `msgs`)."""
    return {i['id']: i for i in ledger.items(task) if i['kind'] == 'message' and i['state'] == 'sent' and i.get('msgs')}


def _edit(task: Task, it: Item) -> tuple[Post | None, str]:
    sent = _sent_messages(task)
    m = sent.get(it.get('ref') or '')
    if not m:
        known = ', '.join(f'{i} ({s["where"]})' for i, s in sent.items()) or 'none'
        return None, f'"id" names no message this task sent (its messages: {known})'
    if not it['text']:
        return None, 'the edit has no new text'
    msgs = m.get('msgs') or []
    return {'edit': m['id'], 'where': m['where'], 'msgs': msgs, 'channel': msgs[0][0], 'text': it['text']}, ''


def sent_list(task: Task) -> str:
    """The messages this task sent, for the agent to edit: '- 3: in #general: "Post-mortem is up…"'."""
    return '\n'.join(f'- {k}: {m["where"]}: "{first_sentence(m["text"], 80)}"' for k, m in _sent_messages(task).items())


def preview_md(post: Post, files: list[str] | None = None) -> str:
    """The preview of a post (files: the paths that go with it)."""
    if post.get('edit'):
        return f'**Edit your message {post["where"]} to:**\n' + quote(post['text'])
    md = f'**To {where(post, md=True)}:**' + ('\n' + quote(post['text']) if post['text'] else '')
    if files:
        md += f'\n_With {attachments.described(files)}_'
    if post.get('poll'):
        md += '\n\n' + polls.describe(post['poll'])
    return md


def offer(task: Task, it: Item) -> None:
    """A ledger message for a channel or people, or an edit: refused, sent at once (this channel, or review off), or a
    preview card for the owner (awaiting_owner). Its files: attachments.py."""
    files = attachments.ready(it)
    post, problem = _target(task, it, bool(files))
    if problem or post is None:
        ledger.move(task, it, 'refused', note=problem)
        return
    it['post'] = post
    here = in_channel(task) and post.get('channel') == task['channel']
    if here or not task.get('preview', True):
        ledger.move(task, it, 'approved', note='this channel' if here else 'review is off')
        send(task, it)
        return
    md = ':outbox_tray: ' + preview_md(post, files)
    if held := attachments.held(it):
        md += f'\n:no_entry: Held back: {held}'
    if machine.party(task)['kind'] != 'owner':
        md += f'\n\nAsked by **{slack.name(machine.party(task)["user"])}**'
    at, at_thread = cases.owner_place(task)
    edit = bool(post.get('edit'))
    ts = slack.app.client.chat_postMessage(
        channel=at,
        thread_ts=at_thread,
        text='Edit this?' if edit else 'Post this?',
        blocks=[
            *(slack.blocks(md, 'Nothing has been changed yet.' if edit else 'Nothing has been posted yet.') or []),
            slack.buttons(
                (
                    'post_send',
                    'Edit it' if edit else 'Send it' if post.get('to') else 'Post it',
                    key_of(task),
                    'primary',
                ),
                (
                    'post_skip',
                    "Don't edit" if edit else "Don't send" if post.get('to') else "Don't post",
                    key_of(task),
                    None,
                ),
            ),
        ],
    )['ts']
    ledger.move(task, it, 'awaiting_owner', card={'ch': at, 'ts': ts}, md=md)
    what = f'an edit of your message {post["where"]}' if edit else f'a message for {where(post)}'
    COMP.event('approval', f'Asked you to check {what}', task=key_of(task))


def decide(task: Task, k: str, send_it: bool, card: str) -> None:
    """The owner's Post / Don't on the preview `card`; a card already decided decides nothing."""
    it = ledger.on_card(task, card)
    if not it or it['state'] != 'awaiting_owner':
        return
    post = it['post']
    line = (
        (':white_check_mark: Editing' if send_it else ':no_entry_sign: Not edited')
        if post.get('edit')
        else (':white_check_mark: Posting' if send_it else ':no_entry_sign: Not posted')
    ) + f' at {say()}'
    slack.app.client.chat_update(channel=it['card']['ch'], ts=card, text=line, blocks=slack.blocks(it['md'], line))
    if send_it:
        ledger.move(task, it, 'approved')
        send(task, it)
    else:
        ledger.move(task, it, 'rejected')
        COMP.event('skipped', 'You chose not to post it', task=k)


def send(task: Task, it: Item) -> None:
    """An approved post or edit, out to Slack: sent or failed."""
    post = it['post']
    if post.get('edit'):
        _apply_edit(task, it, post)
        return
    k = key_of(task)
    dest = where(post)
    at: list[tuple[str, str]] = []
    places: list[tuple[str, str | None]] = []
    ts = ''
    files = attachments.ready(it)
    try:
        if post.get('poll'):
            poll = polls.start(post, k)
            task['poll'], ts = poll['id'], poll['ts']
        else:
            for to in post.get('to') or [post['channel']]:
                dest_id = slack.app.client.conversations_open(users=to)['channel']['id'] if post.get('to') else to
                places.append((dest_id, None))
                if post['text']:
                    ts = slack.app.client.chat_postMessage(
                        channel=dest_id,
                        text=first_sentence(post['text'], 200),
                        blocks=slack.blocks(post['text']),
                        unfurl_links=False,
                    )['ts']
                    at.append((dest_id, ts))
    except Exception as e:
        log('post failed:', e)
        ledger.move(task, it, 'failed', note=f"couldn't send it to {dest}: {str(e)[:200]}")
        return
    if files:
        attachments.upload(it, places)
    link = slack.permalink(post['channel'], ts) if ts and not post.get('to') else None
    what = 'Poll' if post.get('poll') else 'Message'
    sent = f'sent to {dest}' if post.get('to') else f'posted in {dest}'
    if it.get('attachments'):
        sent += f' · files: {attachments.summary(it)}'
    line = f':white_check_mark: {what} {sent}' + (f' · <{link}|open>' if link else '')
    if post.get('poll'):
        line += f' · closes {say(post["poll"]["closes"], "day")}'
        dm, dm_thread = (slack.dm_owner(), None) if in_channel(task) else cases.owner_place(task)
        slack.app.client.chat_postMessage(  # the close button: the owner's only
            channel=dm,
            thread_ts=dm_thread,
            text=f'Poll in {dest}',
            blocks=[
                *(
                    slack.blocks(
                        None,
                        f':bar_chart: {post["poll"]["question"]} · in {dest}' + (f' · <{link}|open>' if link else ''),
                    )
                    or []
                ),
                slack.buttons(('poll_close', 'Close the poll now', task['poll'], None)),
            ],
        )
    slack.note_only(*cases.owner_place(task), line)
    ledger.move(
        task, it, 'sent', where=f'to {dest}' if post.get('to') else f'in {dest}', msgs=at or None, note=f'{what} {sent}'
    )
    COMP.event(
        'sent', f'{what} {sent}', task=k, to=dest, detail=post['poll']['question'] if post.get('poll') else post['text']
    )


def _apply_edit(task: Task, it: Item, post: Post) -> None:
    """Change a message this task sent, everywhere it went."""
    try:
        for at, ts in post['msgs']:
            slack.app.client.chat_update(
                channel=at, ts=ts, text=first_sentence(post['text'], 200), blocks=slack.blocks(post['text'])
            )
    except Exception as e:
        log('edit failed:', e)
        ledger.move(task, it, 'failed', note=f"couldn't edit the message {post['where']}: {str(e)[:200]}")
        return
    if edited := ledger.get(task, post['edit']):  # _edit found it
        edited['text'] = post['text']
    at, ts = post['msgs'][0]
    link = None if at.startswith('D') else slack.permalink(at, ts)
    slack.note_only(
        *cases.owner_place(task),
        f':pencil2: Edited the message {post["where"]}' + (f' · <{link}|open>' if link else ''),
    )
    ledger.move(task, it, 'sent', where=post['where'])
    COMP.event('sent', f'Message edited {post["where"]}', task=key_of(task), to=post['where'], detail=post['text'])


slack.app.action('post_send')(errands.owner_action(lambda t, k, ts: decide(t, k, True, ts), card=True))
slack.app.action('post_skip')(errands.owner_action(lambda t, k, ts: decide(t, k, False, ts), card=True))
