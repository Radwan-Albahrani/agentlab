"""Requests aimed at the owner, seen through their read-only user token (Slack also sends the companion what that token sees).

Restricted mode ("tag", the default): only the owner's own tags count.
  - "@companion" bare, on someone else's message (in their DMs or under their channel message) = an errand for them.
  - "@companion <instructions>" under someone else's channel message = a task right there (once the companion is invited);
    in one of their DMs = a task in their DM with the companion, the conversation as its context.
Team mode adds colleagues asking them (a DM to them, or tagging them): after a short pause for the rest of their
message, one quick model call on the agent's own provider classifies it:
  errand  (strict: an unmistakable small thing such as invoices, access, a document) -> started as an errand
  task    (real work) -> a one-line heads-up in their DM, nothing else
  nothing -> ignored
Dry-run mode ("owner") is team mode where the owner plays the colleague (their self-DM / self-mention)."""

import json
import re
import time

from . import errands, jobs, prompts, reviews, slack, t3, tasks
from .config import COMP, OWNER, REQ_SETTLE, log, mode
from .state import lock, save, state
from .text import first_sentence, quote, without_mention

_pending = {}  # conversation -> request being collected
_known = {}  # cached lookups: channel kinds, members


# ---------------------------------------------------------------- what kind of conversation is this?
def own_dm(ch):
    """Is this DM channel one of the companion's own (vs a DM of the owner's that their user token sees)? Its DM with the
    owner is known directly; other people's DMs with the companion are found by asking Slack, which only answers for
    conversations the companion is in. Failures aren't cached, so a hiccup can't hide the companion's own DM."""
    if ch in _known:
        return _known[ch]
    try:
        if ch == slack.dm_owner():
            _known[ch] = True
            return True
    except Exception as e:
        log('owner DM lookup failed:', e)
    try:
        r = slack.app.client.conversations_members(channel=ch, limit=10)  # fails if the companion isn't in it
        _known[ch] = slack.bot_user() in r.get('members', [])
    except Exception:
        return False
    return _known[ch]


def _self_dm(ch):
    k = 'self:' + ch
    if k not in _known:
        try:
            c = slack.USER.conversations_info(channel=ch)['channel']
            _known[k] = bool(c.get('is_im')) and c.get('user') == OWNER
        except Exception:
            _known[k] = False
    return _known[k]


def team_member(uid):
    """A full member of the workspace (not a bot, guest or Slack Connect user)."""
    k = 'member:' + uid
    if k not in _known:
        try:
            u = slack.app.client.users_info(user=uid)['user']
            _known[k] = not (
                u.get('is_bot') or u.get('deleted') or u.get('is_restricted') or u.get('is_ultra_restricted')
            )
        except Exception:
            _known[k] = False
    return _known[k]


def thread_root_user(ch, tts):
    """Who started this thread (read as the owner, so it works in channels the companion isn't in)."""
    try:
        m = slack.USER.conversations_replies(channel=ch, ts=tts, limit=1)['messages'][0]
        return None if m.get('bot_id') else m.get('user')
    except Exception:
        return None


def bare_tag(text):
    """Just "@companion" (maybe with punctuation): errand mode. Anything more is an instruction: task mode."""
    return not re.sub(r'<@[A-Z0-9]+>|[\s\W_]+', '', text or '')


# ---------------------------------------------------------------- the owner's tags
def tagged_in_thread(ev):
    """The owner tagged @companion under someone else's channel message: bare = errand for them, "review" under a PR
    link = a review of that PR, other words = task."""
    ch, thr = ev['channel'], ev['thread_ts']
    if bare_tag(ev.get('text')):
        log('bare tag in thread', ch, thr, '-> errand')
        owner_tagged(ev)
    elif not slack.bot_in(ch):
        await_invite(ev)
    elif not reviews.from_slack(ch, thr, ev['ts'], ev.get('text', '')):
        log('tag with instructions in thread', ch, thr, '-> task')
        tasks.start(ch, thr, ev['ts'], ev.get('text', ''))


def tagged_in_dm(ev):
    """The owner tagged @companion in one of their DMs (the companion isn't in it): bare = errand for the other person, with
    words = a task for them. The companion can't post there, so the task gets a thread in their DM with the companion, with the
    conversation as its context."""
    if bare_tag(ev.get('text')):
        owner_tagged(ev)
        return
    ch, ts, thr = ev['channel'], ev['ts'], ev.get('thread_ts')
    try:
        if thr:
            msgs = slack.USER.conversations_replies(channel=ch, ts=thr, latest=ts, inclusive=True, limit=60)
            msgs = msgs['messages']
        else:
            msgs = slack.USER.conversations_history(channel=ch, latest=ts, inclusive=True, limit=15)['messages']
            msgs.reverse()  # oldest first
        c = slack.USER.conversations_info(channel=ch)['channel']
        who = slack.name(c['user']) if c.get('user') else c.get('name') or 'a group'
    except Exception as e:
        log('tagged DM unreadable:', e)
        msgs, who = [], 'someone'
    ask = slack.readable(without_mention(ev.get('text'))).strip()
    dm = slack.dm_owner()
    head = slack.post(
        dm,
        None,
        f'From your DM with {who}: {first_sentence(ask, 120)}',
        md=f':inbox_tray: **From your DM with {who}**\n' + quote(ask),
        note='Working on it here. Reply in this thread to steer it.',
    )
    if head:
        log('tag with instructions in a DM', ch, '-> task')
        tasks.start(dm, head, head, ev.get('text', ''), elsewhere=(f'their Slack DM with {who}', msgs))


def owner_tagged(ev):
    """The owner tagged @companion on someone else's request, in one of their DMs (the companion isn't in it; their user token sees
    the tag) or under their channel message. No triage: start on what they asked (their messages since their last
    one); everything comes to their DM, and replies to them wait for their Send."""
    ch, ts, thr = ev['channel'], ev['ts'], ev.get('thread_ts')
    try:
        if thr:
            msgs = list(
                reversed(
                    slack.USER.conversations_replies(channel=ch, ts=thr, latest=ts, inclusive=True, limit=50)[
                        'messages'
                    ]
                )
            )
        else:
            msgs = slack.USER.conversations_history(channel=ch, latest=ts, inclusive=True, limit=15)[
                'messages'
            ]  # newest first
    except Exception as e:
        log('tagged conversation unreadable:', e)
        msgs = []
    theirs = []
    for m in msgs:
        if m.get('user') == OWNER:
            if theirs:
                break
            continue
        if m.get('user') and not m.get('bot_id'):
            theirs.append(m)
    own = slack.readable(without_mention(ev.get('text'))).strip()
    texts = [slack.readable(m.get('text') or '') for m in reversed(theirs)] or [own or '(see the conversation)']
    if own and theirs:
        texts.append(f'({slack.name(OWNER)} added: {own})')
    p = {
        'ch': ch,
        'ts': theirs[0]['ts'] if theirs else ts,
        'thread_ts': thr,
        'user': theirs[0]['user'] if theirs else OWNER,
        'tagged': True,
        'im': ev.get('channel_type') in ('im', 'mpim'),
        'texts': texts,
        'files': [f for m in theirs for f in m.get('files') or []],
    }
    log('tagged by owner in', ch, 'for', p['user'])
    errands.start(p, own)


def await_invite(ev):
    """Tagged in a channel the companion isn't in: Slack offers the owner to invite it. Keep the tag and start as soon as
    the companion is a member (checked by the poller); dropped after a day. Never moved to a DM instead."""
    with lock:
        state.setdefault('awaiting_invite', {})[ev['ts']] = {
            'ch': ev['channel'],
            'thread_ts': ev.get('thread_ts'),
            'ts': ev['ts'],
            'text': ev.get('text', ''),
            'at': time.time(),
        }
    save()
    log('tagged in', ev['channel'], 'but not a member: waiting for the invite')


def invite_tick():
    waiting = state.get('awaiting_invite') or {}
    if not waiting or time.time() < state.get('_invite_check', 0):
        return
    state['_invite_check'] = time.time() + 15
    for ts, w in list(waiting.items()):
        if time.time() - w['at'] > 86400:
            waiting.pop(ts, None)
        elif slack.bot_in(w['ch']):
            waiting.pop(ts, None)
            log('invited to', w['ch'], ': starting the waiting tag')
            jobs.run_later(tasks.start, w['ch'], w['thread_ts'] or ts, ts, w['text'])


# ---------------------------------------------------------------- colleagues asking the owner (team / dry run)
def notice(ev):
    """A message the companion wasn't addressed in: is it someone asking the owner for something?"""
    m = mode()
    if m not in ('owner', 'team') or not slack.USER:
        return
    ch, ts, user, text = ev['channel'], ev['ts'], ev.get('user'), ev.get('text') or ''
    im = ch.startswith('D')
    if m == 'owner':  # dry run: the owner plays the colleague
        ok = user == OWNER and ((im and _self_dm(ch)) or (not im and f'<@{OWNER}>' in text))
    else:
        ok = user != OWNER and (im or f'<@{OWNER}>' in text) and team_member(user)
    if not ok:
        return
    conv = (ch, ev.get('thread_ts') or ('dm' if im else ts))
    with lock:
        p = _pending.setdefault(
            conv,
            {'ch': ch, 'ts': ts, 'thread_ts': ev.get('thread_ts'), 'user': user, 'im': im, 'texts': [], 'files': []},
        )
        p['texts'].append(slack.readable(text))
        p['files'] += ev.get('files') or []
        p['last'] = time.time()
    log('request seen from', user, 'in', ch)


def pending_tick():
    now = time.time()
    for conv, p in list(_pending.items()):
        if now - p['last'] >= REQ_SETTLE:
            _pending.pop(conv, None)
            jobs.run_later(triage, p)


def triage(p):
    """Most messages are just conversation: one quick model call decides, and only clear errands start an agent."""
    who, owner = slack.name(p['user']), slack.name(OWNER)
    try:
        msgs = list(reversed(slack.USER.conversations_history(channel=p['ch'], latest=p['ts'], limit=8)['messages']))
    except Exception:
        msgs = []
    convo = '\n'.join(f'{slack.name(m.get("user", "?"))}: {slack.readable(m.get("text") or "")[:400]}' for m in msgs)
    res = t3.triage(prompts.triage(owner, who, convo, p['texts']))
    found = re.search(r'\{.*\}', str(res.get('result') or ''), re.S)
    try:
        verdict = json.loads(found.group(0)) if found else {}
    except ValueError:
        verdict = {}
    kind = verdict.get('kind') or ('errand' if verdict.get('act') else 'nothing' if verdict else '')
    what = verdict.get('what') or ''
    log('triage', p['user'], p['ch'], kind or res.get('result'))
    if kind == 'errand':
        errands.start(p, what)
    elif kind == 'task':
        _heads_up(p, who, what)
    elif not kind:  # triage broke: tell the owner rather than drop it
        slack.post(
            slack.dm_owner(),
            None,
            f'{who} messaged you',
            md=f":grey_question: Couldn't check whether **{who}**'s"
            ' message needs anything. Tag me in that conversation if it does.',
        )


def _heads_up(p, who, what):
    """A bigger ask: the owner decides. One line in their DM; the companion does nothing unless they tag it there."""
    link = slack.permalink(p['ch'], p['ts'], slack.USER)
    slack.post(
        slack.dm_owner(),
        None,
        f'{who} asked you: {what}',
        md=f':bulb: **{who}** asked you: {what or "(see the message)"}' + (f' · <{link}|open>' if link else ''),
        note='Looks like a bigger task, so I left it to you. Tag me there if you want me on it.',
    )
    COMP.event('noticed', f'{who} asked you: {what}'[:200], to=None, detail='heads-up only; left to you')
