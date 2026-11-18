"""The requests channel (a hub setting): colleagues post asks there, the owner approves or declines each in their DM.

An approved ask runs as the colleague's task in its thread (a pull request link: a review they follow); a declined one
is told so. The card is the ask's case (see cases.py): while it is pending the owner's replies under it go to the
colleague; once taken on they are the owner talking to the companion, privately."""

from . import jobs, machine, requests, reviews, slack, tasks
from .config import COMP, OWNER, log, mode
from .state import key, lock, save, state
from .text import first_sentence, quote


def _asks():
    return state.setdefault('inbox', {})


def route(ev, mentioned):
    """Handle a message in the requests channel; False leaves it to the usual routing.

    Only tags count, top level or in a thread: people discuss things there too."""
    ch, ts, user, thr = ev['channel'], ev['ts'], ev.get('user'), ev.get('thread_ts')
    if not user or user == OWNER or mode() == 'owner':
        return False
    if not mentioned:
        return True
    if not thr:
        if requests.team_member(user):
            jobs.run_later(ask, ev)
        return True
    task = state['tasks'].get(key(ch, thr))
    if task and machine.is_colleague(task) and machine.party(task)['user'] == user:
        jobs.run_later(tasks.follow_up, task, ev.get('text', ''), ev.get('files'), ts, user)
        return True
    a = _asks().get(key(ch, thr))
    if a and a['user'] == user and a['status'] == 'pending':
        jobs.run_later(_added, a, ev.get('text', ''))
        return True
    return False


def ask(ev):
    ch, ts, user = ev['channel'], ev['ts'], ev['user']
    text = slack.ask(ev.get('text') or '').strip()
    who, owner = slack.name(user), slack.name(OWNER)
    link = slack.permalink(ch, ts)
    card = slack.post(
        slack.dm_owner(),
        None,
        f'{who} asked: {first_sentence(text, 120)}',
        md=f':inbox_tray: **{who}** asked in <#{ch}>' + (f' · <{link}|open>' if link else '') + '\n' + quote(text),
    )
    if not card:
        slack.post(ch, ts, 'Not sent', md=f":warning: I couldn't pass this on to {owner}. Try again later.")
        return
    a = {'ch': ch, 'ts': ts, 'user': user, 'name': who, 'text': text, 'card': card, 'status': 'pending'}
    with lock:
        _asks()[key(ch, ts)] = a
        _show(a)
    slack.react(ch, ts, 'hourglass_flowing_sand')
    a['ack'] = slack.note_only(ch, ts, f':hourglass_flowing_sand: Sent to {owner} for approval. I will reply here.')
    save()
    log('request from', user, 'in', ch)
    COMP.event('noticed', f'{who} asked: {first_sentence(text, 80)}', detail='waiting for your approval')


def _show(a):
    """The owner's card: the ask with Approve / Decline while pending, its outcome after."""
    head = f':inbox_tray: **{a["name"]}** asked in <#{a["ch"]}>\n' + quote(a['text'])
    k = key(a['ch'], a['ts'])
    if a['status'] == 'pending':
        note = 'Reply in this thread to message them.'
        buttons = slack.buttons(('inbox_approve', 'Approve', k, 'primary'), ('inbox_decline', 'Decline', k, 'danger'))
        blocks = [*slack.blocks(head, note), buttons]
    else:
        note = {
            'approved': ':white_check_mark: Approved: working on it in their thread',
            'declined': ':no_entry_sign: Declined',
        }[a['status']]
        tail = ' · reply here to talk to me about it; they see nothing of it' if a['status'] == 'approved' else ''
        blocks = slack.blocks(head, note + tail)
    slack.app.client.chat_update(channel=slack.dm_owner(), ts=a['card'], text=f'{a["name"]} asked', blocks=blocks)


def _added(a, text):
    """The colleague added to a pending ask: it joins the ask, and the owner sees it under the card."""
    more = slack.ask(text).strip()
    if not more:
        return
    with lock:
        a['text'] += '\n' + more
        _show(a)
        save()
    slack.post(
        slack.dm_owner(), a['card'], f'{a["name"]} added: {more[:100]}', md=f'**{a["name"]}** added:\n' + quote(more)
    )


def decide(k, approve):
    with lock:
        a = _asks().get(k)
        if not a or a['status'] != 'pending':
            return
        a['status'] = 'approved' if approve else 'declined'
        _show(a)
        save()
    slack.react(a['ch'], a['ts'], 'hourglass_flowing_sand', remove=True)
    owner = slack.name(OWNER)
    if not approve:
        slack.post(a['ch'], a['ts'], 'Declined', md=f':no_entry_sign: {owner} declined this request.')
        COMP.event('sent', f'Declined the request of {a["name"]}', to=a['name'], detail=first_sentence(a['text'], 120))
        return
    slack.note_only(a['ch'], a['ts'], f':white_check_mark: {owner} approved this. Starting now.')
    how = {'via': f'in the requests channel #{slack.channel_name(a["ch"])}'}
    if not reviews.from_slack(
        a['ch'], a['ts'], a['ts'], a['text'], by=a['user'], any_words=True, approved_by=OWNER, **how
    ):
        tasks.start(a['ch'], a['ts'], a['ts'], a['text'], guest=a['user'], approved=a['card'], **how)


def card_of(channel, thread_ts):
    """The ask whose card is this message in the owner's DM, or None."""
    if channel != slack.dm_owner():
        return None
    return next((a for a in _asks().values() if a['card'] == thread_ts), None)


def relay(a, text, ts):
    """The owner's reply under an ask's card, passed on to the colleague's thread."""
    said = slack.readable(text).strip()
    if said and slack.post(
        a['ch'], a['ts'], f'{slack.name(OWNER)}: {said[:100]}', md=f'**{slack.name(OWNER)}:** {said}'
    ):
        slack.react(slack.dm_owner(), ts, 'white_check_mark')


def _decide_action(approve):
    def run(ack, body):
        ack()
        if body['user']['id'] == OWNER:
            decide(body['actions'][0].get('value') or '', approve)

    return run


slack.app.action('inbox_approve')(_decide_action(True))
slack.app.action('inbox_decline')(_decide_action(False))
