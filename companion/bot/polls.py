"""Public button polls the companion runs in a channel; state['polls'][id].votes: user -> chosen option indexes."""

import re
import secrets
import time
from datetime import datetime

from . import slack
from .config import COMP, OWNER, log
from .state import lock, save, state
from .text import clock

BAR = 10  # characters of the longest bar
AVATARS = 9  # Slack context rows hold max 10 elements: pictures + one names element


def describe(poll):
    """The poll as preview text."""
    when = clock(poll['closes'], date=True)
    return (
        f':bar_chart: **{poll["question"]}**\n'
        + '\n'.join(f'- {o}' for o in poll['options'])
        + ('\n_People can pick as many as they like._' if poll.get('multiple') else '')
        + f'\n\nCloses {when}; the winner is announced in the channel.'
    )


def counts(poll):
    n = [0] * len(poll['options'])
    for chosen in poll['votes'].values():
        for i in chosen:
            n[i] += 1
    return n


def voters(poll):
    return sum(1 for chosen in poll['votes'].values() if chosen)


def _people(k):
    return f'{k} {"person" if k == 1 else "people"}'


def who(poll, i):
    """Voters for option i, in voting order."""
    return [u for u, chosen in poll['votes'].items() if i in chosen]


def voter(poll, u):
    """A voter's name, marked when the owner added the vote."""
    by = poll.get('added_by', {}).get(u)
    return slack.name(u) + (f' (added by {slack.name(by)})' if by else '')


def _voters_line(poll, people):
    """Context row under an option: up to AVATARS pictures, then the names."""
    pics = [
        {'type': 'image', 'image_url': slack.avatar(u), 'alt_text': slack.name(u)} for u in people if slack.avatar(u)
    ][:AVATARS]
    names = ', '.join(voter(poll, u) for u in people)
    return {'type': 'context', 'elements': [*pics, {'type': 'mrkdwn', 'text': names[:2900]}]}


def _blocks(poll):
    n = counts(poll)
    top = max(n) or 1
    state_ = f'closes {clock(poll["closes"])}' if poll['open'] else 'closed'
    intro = (poll['text'] + '\n\n' if poll['text'] else '') + f':bar_chart: **{poll["question"]}** · {state_}'
    b = slack.blocks(intro)
    for i, (o, c) in enumerate(zip(poll['options'], n, strict=True)):
        b += slack.blocks(f'**{o}**  `{"█" * round(BAR * c / top) or "·"}` {c} vote{"s" if c != 1 else ""}')
        if c:
            b.append(_voters_line(poll, who(poll, i)))
    how = (
        'pick as many as you like, press one again to take it back'
        if poll.get('multiple')
        else 'press your choice again to take your vote back'
    )
    b += slack.blocks(None, f'{_people(voters(poll))} voted' + (f' · {how}' if poll['open'] else ''))
    if poll['open']:
        b.append(
            slack.buttons(*((f'poll_vote_{i}', o, f'{poll["id"]}:{i}', None) for i, o in enumerate(poll['options'])))
        )
    return b


def start(post, task_key):
    """Post the poll in its channel; returns it with its message ts."""
    poll = {
        'id': secrets.token_hex(4),
        'channel': post['channel'],
        'text': post['text'],
        **post['poll'],
        'votes': {},
        'open': True,
        'task': task_key,
    }
    poll['ts'] = slack.app.client.chat_postMessage(
        channel=poll['channel'], text=poll['question'], blocks=_blocks(poll), unfurl_links=False
    )['ts']
    with lock:
        state['polls'][poll['id']] = poll
    save()
    log('poll started', poll['id'], poll['channel'])
    return poll


def _refresh(poll):
    slack.app.client.chat_update(channel=poll['channel'], ts=poll['ts'], text=poll['question'], blocks=_blocks(poll))


def migrate():
    """Convert legacy single-index votes to multiple-choice lists."""
    for poll in state['polls'].values():
        if 'multiple' in poll:
            continue
        poll['votes'] = {u: v if isinstance(v, list) else [v] for u, v in poll['votes'].items()}
        poll['multiple'] = True
        if poll['open']:
            _refresh(poll)
        log('poll made multiple choice', poll['id'])
    save()


def vote(poll, user, i):
    if not poll['open'] or not 0 <= i < len(poll['options']):
        return
    mine = poll['votes'].get(user, [])
    if i in mine:
        mine = [x for x in mine if x != i]
    elif poll.get('multiple'):
        mine = [*mine, i]  # keep pick order: switching to single choice keeps the latest
    else:
        mine = [i]
    if mine:
        poll['votes'][user] = mine
    else:
        poll['votes'].pop(user, None)
    save()
    _refresh(poll)


def for_prompt(channel='', thread_ts=''):
    """The open polls as prompt text for the agent."""
    open_polls = [p for p in state['polls'].values() if p['open']]
    if not open_polls:
        return ''
    lines = [
        f'- {p["id"]}: "{p["question"]}" in channel {p["channel"]}, '
        + ('multiple choice' if p.get('multiple') else 'single choice')
        + datetime.fromtimestamp(p['closes']).astimezone().strftime(', closes %Y-%m-%dT%H:%M%z')
        + (' (THIS thread is under it)' if p['channel'] == channel and p['ts'] == thread_ts else '')
        for p in open_polls
    ]
    return '\n\nOpen polls the companion is running:\n' + '\n'.join(lines)


def _thread_for(poll):
    """The poll's task thread, else the owner's DM."""
    task = state['tasks'].get(poll['task'])
    return (task['channel'], task['thread_ts']) if task else (slack.dm_owner(), None)


def change(c, task=None):
    """Apply a poll change from poll-change.json or the hub (task None): choice mode, closing time, close now."""
    poll = state['polls'].get(str(c.get('poll') or ''))
    if not poll:
        return
    ch, tts = (task['channel'], task['thread_ts']) if task else _thread_for(poll)
    if c.get('close') and poll['open']:
        close(poll, by=OWNER)
        return
    if not poll['open']:
        slack.post(ch, tts, 'Poll not changed', md=':warning: That poll is already closed.')
        return
    closes = None
    if c.get('closes'):
        try:  # epoch from the hub, ISO 8601 from the agent
            closes = (
                float(c['closes'])
                if isinstance(c['closes'], int | float)
                else datetime.fromisoformat(str(c['closes'])).timestamp()
            )
        except ValueError:
            closes = 0
        if closes <= time.time():
            slack.post(ch, tts, 'Poll not changed', md=':warning: The new closing time must be in the future.')
            return
    done = []
    if 'multiple' in c and bool(c['multiple']) != bool(poll.get('multiple')):
        poll['multiple'] = bool(c['multiple'])
        trimmed = 0
        if not poll['multiple']:
            for u, chosen in poll['votes'].items():
                if len(chosen) > 1:
                    poll['votes'][u], trimmed = chosen[-1:], trimmed + 1
        done.append(
            ('now multiple choice' if poll['multiple'] else 'now single choice')
            + (f' ({_people(trimmed)} had several picks; their latest was kept)' if trimmed else '')
        )
    if closes and closes != poll['closes']:
        poll['closes'] = closes
        done.append(f'now closes {clock(closes)}')
    if 'text' in c and str(c['text'] or '').strip()[:3000] != poll['text']:
        poll['text'] = str(c['text'] or '').strip()[:3000]
        done.append('new intro')
    if c.get('vote'):
        line, ok = _vote_for(poll, c['vote'])
        if not ok:
            slack.post(ch, tts, 'Vote not added', md=f':warning: {line}')
            return
        done.append(line)
    if not done:
        slack.note_only(ch, tts, f':bar_chart: "{poll["question"]}" already is like that; nothing changed.')
        return
    save()
    _refresh(poll)
    where = '#' + (slack.channel_name(poll['channel']) or poll['channel'])
    line = f':bar_chart: Poll in {where} updated: ' + '; '.join(done) + ('' if task else ' (from the hub)')
    slack.note_only(ch, tts, line)
    if task:
        task['posted'] = True  # suppresses the agent's own answer in the thread
    COMP.event('settings', f'Poll changed: {" and ".join(done)}', task=poll['task'], to=where, detail=poll['question'])
    log('poll changed', poll['id'], done)


def _vote_for(poll, v):
    """Owner adds/removes someone's vote -> (line, ok); the person is looked up by name, never an agent-given id."""
    uid, problem = slack.find_user(str(v.get('for') or ''))
    if not uid:
        return problem, False
    who_ = slack.name(uid)
    if v.get('remove'):
        poll['votes'].pop(uid, None)
        poll.get('added_by', {}).pop(uid, None)
        return f"removed {who_}'s vote", True
    labels = {o.casefold(): i for i, o in enumerate(poll['options'])}
    picks = []
    for want in v.get('options') or []:
        w = str(want).strip().casefold()
        hits = [i for label, i in labels.items() if label == w] or [
            i for label, i in labels.items() if w and w in label
        ]
        if len(hits) != 1:
            return f'"{want}" is not one of the options ({", ".join(poll["options"])}).', False
        picks.append(hits[0])
    picks = list(dict.fromkeys(picks))
    if not picks or (len(picks) > 1 and not poll.get('multiple')):
        return 'Name one option (this poll is single choice).' if picks else 'Name the option to vote for.', False
    poll['votes'][uid] = picks
    poll.setdefault('added_by', {})[uid] = OWNER
    return f"added {who_}'s vote for {', '.join(poll['options'][i] for i in picks)}", True


def result(poll):
    n, people = counts(poll), voters(poll)
    best = max(n)
    winners = [o for o, c in zip(poll['options'], n, strict=True) if c == best]
    if not people:
        return f':ballot_box_with_ballot: **{poll["question"]}**: no votes came in.'
    if len(winners) > 1:
        head = f':handshake: A tie between {" and ".join(f"**{w}**" for w in winners)}, {best} votes each.'
    elif poll.get('multiple'):
        head = f':trophy: **{winners[0]}** wins: {best} of the {_people(people)} who voted picked it.'
    else:
        head = f':trophy: **{winners[0]}** wins with {best} of {people} vote{"s" if people != 1 else ""}.'
    rows = sorted(enumerate(zip(poll['options'], n, strict=True)), key=lambda x: -x[1][1])
    table = '\n'.join(
        f'- {o}: {c}' + (f' ({", ".join(voter(poll, u) for u in who(poll, i))})' if c else '') for i, (o, c) in rows
    )
    return f'{head}\n\n_{poll["question"]}_\n{table}'


def close(poll, by=''):
    """Remove the buttons and announce the result."""
    if not poll['open']:
        return
    poll['open'] = False
    poll['closed'] = time.time()
    save()
    _refresh(poll)
    text = result(poll)
    slack.app.client.chat_postMessage(
        channel=poll['channel'],
        thread_ts=poll['ts'],
        reply_broadcast=True,
        text=re.sub(r'[*_:]', '', text.split('\n')[0]),
        blocks=slack.blocks(text),
    )
    where = '#' + (slack.channel_name(poll['channel']) or poll['channel'])
    task = state['tasks'].get(poll['task'])
    line = f':bar_chart: Poll closed in {where}' + (' by you' if by else '') + ': ' + text.split('\n')[0]
    if task:
        slack.note_only(task['channel'], task['thread_ts'], line)
        task['closed'] = line
    COMP.event('sent', f'Poll result in {where}', task=poll['task'], to=where, detail=text)
    log('poll closed', poll['id'])
    save()


def card(poll):
    """The hub's poll card (see companion.py)."""
    n = counts(poll)
    return {
        'id': poll['id'],
        'task': poll['task'],
        'open': poll['open'],
        'closes': poll['closes'],
        'closed': poll.get('closed'),
        'question': poll['question'],
        'channel': '#' + (slack.channel_name(poll['channel']) or poll['channel']),
        'link': slack.link(poll['channel'], poll['ts']),
        'multiple': bool(poll.get('multiple')),
        'options': [
            {
                'label': o,
                'votes': c,
                'voters': [{'name': voter(poll, u), 'avatar': slack.avatar(u)} for u in who(poll, i)],
            }
            for i, (o, c) in enumerate(zip(poll['options'], n, strict=True))
        ],
    }


def summary(poll):
    when = clock(poll['closes'])
    return f'Poll open until {when} · {_people(voters(poll))} voted'


def tick():
    now = time.time()
    for poll in list(state['polls'].values()):
        if poll['open'] and now >= poll['closes']:
            close(poll)


@slack.app.action(re.compile(r'^poll_vote_\d+$'))
def on_vote(ack, body):
    ack()
    pid, _, i = body['actions'][0]['value'].rpartition(':')
    with lock:
        poll = state['polls'].get(pid)
        if poll:
            vote(poll, body['user']['id'], int(i))


@slack.app.action('poll_close')
def on_close(ack, body):
    ack()
    if body['user']['id'] != OWNER:
        return
    with lock:
        poll = state['polls'].get(body['actions'][0]['value'])
        if poll and poll['open']:
            close(poll, by=OWNER)
            slack.update(body['channel']['id'], body['container']['message_ts'], 'Poll closed', note='Poll closed.')
