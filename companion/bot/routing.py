"""Routes each Slack message; only the owner gives work, anyone else addressing the bot gets one refusal."""

from . import drafts, jobs, requests, reviews, slack, tasks
from .config import OWNER
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
    slack.post(channel, thread_ts, f'Hi <@{user}>, I only take tasks from <@{OWNER}>.')


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
        and requests.thread_root_user(ch, thr) not in (OWNER, None)
    ):
        jobs.run_later(requests.tagged_in_thread, ev)
        return
    if not (mentioned or (in_dm and requests.own_dm(ch))):
        requests.notice(ev)
        return
    if user != OWNER:
        if not in_dm or requests.own_dm(ch):
            _refuse(ch, tts, user)
        return
    dkey, draft = drafts.for_thread(ch, tts)
    if draft and thr:
        jobs.run_later(drafts.revise, dkey, draft, ev.get('text', ''), ts)
        return
    task = state['tasks'].get(key(ch, tts))
    if task and (mentioned or in_dm):
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
