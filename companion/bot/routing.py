"""Routes each Slack message; the owner and people they gave access give work, anyone else gets one refusal."""

from . import cases, drafts, inbox, jobs, machine, requests, reviews, slack, tasks
from .config import COMP, OWNER, has_access, log, mode, requests_channel
from .shapes import Json
from .state import key, save, state

_seen: list[str] = []
IGNORED = ('message_changed', 'message_deleted', 'bot_message', 'channel_join')


def _once(ts: str) -> bool:
    if ts in _seen:
        return False
    _seen.append(ts)
    del _seen[:-500]
    return True


def _refuse(channel: str, thread_ts: str, user: str | None) -> None:
    k = key(channel, thread_ts)
    if k in state['refused']:
        return
    state['refused'].append(k)
    save()
    can = ', but I can review a pull request: send me its GitHub link' if _reviews_from(user) else ''
    slack.post(channel, thread_ts, f'Hi <@{user}>, I only take tasks from <@{OWNER}>{can}.')


def _reviews_from(user: str | None) -> bool:
    """Can this colleague ask for pull request reviews (the hub's setting; never in dry run)?"""
    who = COMP.setting('review_requests')
    if user == OWNER or mode() == 'owner' or who == 'off':
        return False
    return has_access(user) or (who == 'team' and user is not None and requests.team_member(user))


def _bot_reads(ev: Json) -> bool:
    """Can the bot read and post where this message is?"""
    if ev.get('channel_type') in ('im', 'mpim') or ev['channel'].startswith('D'):
        return requests.own_dm(ev['channel'])
    return slack.bot_in(ev['channel'])


def tagged_by_edit(ev: Json) -> Json | None:
    """An edit that adds the companion's tag to a message: the message as it is now, or None. Only the tag counts:
    other edits change nothing already asked."""
    if ev.get('subtype') != 'message_changed':
        return None
    new, old, tag = ev.get('message') or {}, ev.get('previous_message') or {}, f'<@{slack.bot_user()}>'
    if new.get('bot_id') or tag not in (new.get('text') or '') or tag in (old.get('text') or ''):
        return None
    return dict(new, channel=ev['channel'], channel_type=ev.get('channel_type'))


def route(ev: Json, mentioned: bool) -> None:
    edited = tagged_by_edit(ev)
    if edited:
        log('tag added by an edit', ev['channel'], edited['ts'])
        ev, mentioned, once = edited, True, edited['ts'] + ':tagged'
    else:
        once = ev.get('ts')
    if ev.get('bot_id') or ev.get('subtype') in IGNORED:
        return
    ch, ts, user = ev['channel'], ev['ts'], ev.get('user')
    in_dm, thr = ch.startswith('D'), ev.get('thread_ts')
    tts = thr or ts
    if not _once(once):
        return
    followed = thr and state['tasks'].get(key(ch, thr))
    if followed:  # a case follows its whole thread, whoever writes and whether or not they tag the companion
        cases.in_thread(followed, ev)
    if ch == requests_channel() and inbox.route(ev, mentioned):
        return
    owner_tag = mentioned and user == OWNER and slack.USER
    if owner_tag and ev.get('channel_type') in ('im', 'mpim') and not requests.own_dm(ch):
        jobs.run_later(requests.tagged_in_dm, ev)
        return
    if (
        owner_tag
        and thr
        and not in_dm
        and key(ch, thr) not in state['tasks']
        and not reviews.in_thread(ch, thr)
        and requests.thread_root_user(ch, thr) not in (OWNER, None)
    ):
        jobs.run_later(requests.tagged_in_thread, ev)
        return
    if not (mentioned or (in_dm and requests.own_dm(ch))):
        requests.notice(ev)
        return
    if (
        user != OWNER
        and key(ch, tts) not in state['tasks']
        and _reviews_from(user)
        and _bot_reads(ev)
        and reviews.from_slack(ch, tts, ts, ev.get('text', ''), by=user, any_words=not has_access(user))
    ):
        return
    if not has_access(user):
        if not in_dm or requests.own_dm(ch):
            _refuse(ch, tts, user)
        return
    if user != OWNER:
        task = state['tasks'].get(key(ch, tts))
        if not task and mentioned and slack.USER and not _bot_reads(ev):
            jobs.run_later(requests.guest_tagged, ev)
            return
        if task:
            jobs.run_later(tasks.follow_up, task, ev.get('text', ''), ev.get('files'), ts, 'thread', user)
        elif mentioned or not thr:
            jobs.run_later(tasks.start, ch, tts, ts, ev.get('text', ''), None, user)
        return
    case = in_dm and thr and key(ch, thr) not in state['tasks'] and cases.at(ch, thr)
    if case and not ev.get('files') and tasks.is_side_question(slack.ask(ev.get('text', '')).strip()):
        jobs.run_later(tasks.side_reply, case, slack.ask(ev.get('text', '')).strip(), ts, 'case')
        return
    if case and machine.running(case) and machine.asking(case):  # the agent asked the owner there: the answer
        cases.heard(case, OWNER, ev.get('text', ''), ev.get('files'), private=True)
        jobs.run_later(tasks.follow_up, case, ev.get('text', ''), ev.get('files'), ts, 'case')
        return
    if case:  # the owner talking to the companion about a colleague's conversation: private
        jobs.run_later(cases.ask, case, ev.get('text', ''), ev.get('files'), ts)
        return
    card = in_dm and thr and inbox.card_of(ch, thr)
    if card:  # an ask not taken on (yet): the owner's words go to the colleague
        jobs.run_later(inbox.relay, card, ev.get('text', ''), ts)
        return
    dkey, draft = drafts.for_thread(ch, tts)
    if draft and thr and dkey is not None:
        jobs.run_later(drafts.revise, dkey, draft, ev.get('text', ''), ts)
        return
    task = state['tasks'].get(key(ch, tts))
    review = thr and (mentioned or in_dm) and reviews.for_reply(ch, thr, ev.get('text', ''), others=bool(task))
    if review == 'which':
        jobs.run_later(reviews.which, ch, tts)  # tts is thr here: a review only answers in a thread
    elif review:
        jobs.run_later(reviews.answer, review, ev.get('text', ''), ev.get('files'), ts)
    elif task and (mentioned or in_dm):
        jobs.run_later(tasks.follow_up, task, ev.get('text', ''), ev.get('files'), ts, 'thread')
    elif mentioned and not in_dm and not slack.bot_in(ch):
        requests.await_invite(ev)
    elif (mentioned or (in_dm and not thr)) and not reviews.from_slack(ch, tts, ts, ev.get('text', '')):
        jobs.run_later(tasks.start, ch, tts, ts, ev.get('text', ''))


def replay(channel: str) -> None:
    """Handle a DM's messages since the companion's last reply, oldest first: ones it missed (it couldn't see them)."""
    missed: list[Json] = []
    for m in slack.app.client.conversations_history(channel=channel, limit=20)['messages']:  # newest first
        if m.get('bot_id') or m.get('user') == slack.bot_user():
            break
        missed.append(m)
    for m in reversed(missed):
        route(dict(m, channel=channel, channel_type='im'), f'<@{slack.bot_user()}>' in (m.get('text') or ''))
    log('replayed', channel, len(missed))


@slack.app.event('app_mention')
def on_mention(event: Json) -> None:
    route(event, True)


@slack.app.event('message')
def on_message(event: Json) -> None:
    route(event, f'<@{slack.bot_user()}>' in (event.get('text') or ''))
