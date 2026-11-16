"""Routes each Slack message; the owner and people they gave access give work, anyone else gets one refusal."""

from . import drafts, jobs, requests, reviews, slack, tasks
from .config import COMP, OWNER, has_access, mode
from .state import key, save, state

_seen = []
IGNORED = ('message_changed', 'message_deleted', 'bot_message', 'channel_join')


def _once(ts):
    if ts in _seen:
        return False
    _seen.append(ts)
    del _seen[:-500]
    return True


def _refuse(channel, thread_ts, user):
    k = key(channel, thread_ts)
    if k in state['refused']:
        return
    state['refused'].append(k)
    save()
    can = ', but I can review a pull request: send me its GitHub link' if _reviews_from(user) else ''
    slack.post(channel, thread_ts, f'Hi <@{user}>, I only take tasks from <@{OWNER}>{can}.')


def _reviews_from(user):
    """Can this colleague ask for pull request reviews (the hub's setting; never in dry run)?"""
    who = COMP.setting('review_requests')
    if user == OWNER or mode() == 'owner' or who == 'off':
        return False
    return has_access(user) or (who == 'team' and requests.team_member(user))


def _bot_reads(ev):
    """Can the bot read and post where this message is?"""
    if ev.get('channel_type') in ('im', 'mpim') or ev['channel'].startswith('D'):
        return requests.own_dm(ev['channel'])
    return slack.bot_in(ev['channel'])


def route(ev, mentioned):
    if ev.get('bot_id') or ev.get('subtype') in IGNORED:
        return
    ch, ts, user = ev['channel'], ev['ts'], ev.get('user')
    in_dm, thr = ch.startswith('D'), ev.get('thread_ts')
    tts = thr or ts
    if not _once(ts):
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
            jobs.run_later(tasks.follow_up, task, ev.get('text', ''), ev.get('files'), ts, user)
        elif mentioned or not thr:
            jobs.run_later(tasks.start, ch, tts, ts, ev.get('text', ''), None, user)
        return
    dkey, draft = drafts.for_thread(ch, tts)
    if draft and thr:
        jobs.run_later(drafts.revise, dkey, draft, ev.get('text', ''), ts)
        return
    task = state['tasks'].get(key(ch, tts))
    review = thr and (mentioned or in_dm) and reviews.for_reply(ch, thr, ev.get('text', ''), others=bool(task))
    if review == 'which':
        jobs.run_later(reviews.which, ch, thr)
    elif review:
        jobs.run_later(reviews.answer, review, ev.get('text', ''), ev.get('files'), ts)
    elif task and (mentioned or in_dm):
        jobs.run_later(tasks.follow_up, task, ev.get('text', ''), ev.get('files'), ts)
    elif mentioned and not in_dm and not slack.bot_in(ch):
        requests.await_invite(ev)
    elif (mentioned or (in_dm and not thr)) and not reviews.from_slack(ch, tts, ts, ev.get('text', '')):
        jobs.run_later(tasks.start, ch, tts, ts, ev.get('text', ''))


@slack.app.event('app_mention')
def on_mention(event):
    route(event, True)


@slack.app.event('message')
def on_message(event):
    route(event, f'<@{slack.bot_user()}>' in (event.get('text') or ''))
