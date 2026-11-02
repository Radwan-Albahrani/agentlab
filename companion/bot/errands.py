"""Errands: someone asked the owner for something (invoices, access, a document) and the agent does it as them.

Everything happens in a thread of the owner's DM with the companion, headed by one message ("X asked you", Stop button):
  start()             -> that head message + a T3 chat with the request and its conversation
  outbox.tick()       -> the agent's files / approval request / temporary login arrive through the gate
  ask_approval()      -> Approve / Reject for anything sensitive; the decision goes back to the chat
  reply_requester()   -> the answer for whoever asked waits for the owner's Send (or goes out with an approval)
  ask_credential()    -> a temporary first-login password, sent to them privately only after the owner's tap
  close_head()        -> when it ends, the head message loses its Stop button and says how it ended
Nobody but the owner can press any of these buttons. In dry-run mode nothing ever reaches anyone else."""

from datetime import datetime

from . import jobs, prompts, slack, t3, tasks
from .config import COMP, NAME, OWNER, default_project, log, mode
from .state import key, lock, new_task, save, state
from .text import first_sentence, quote


def start(p, what=''):
    """p: the request: ch, ts, thread_ts, user (who asked), im, texts, files, tagged (the owner tagged the companion on it)."""
    who, ch = slack.name(p['user']), p['ch']
    asked = '\n'.join(p['texts']).strip()
    link = slack.permalink(ch, p['ts'], slack.USER)
    how = 'asked you' if p.get('tagged') else 'DMed you' if p['im'] else 'mentioned you'
    dm = slack.dm_owner()
    md = (
        f':eyes: **{who}** {how}'
        + (f': {what}' if what else '')
        + (f' · <{link}|open>' if link else '')
        + '\n'
        + quote(first_sentence(asked, 400))
    )
    head = slack.app.client.chat_postMessage(
        channel=dm,
        text=f'{who} {how}: {first_sentence(asked, 120)}',
        blocks=[
            *slack.blocks(md, 'Working on it. Sensitive changes wait for your approval here.'),
            slack.buttons(('errand_stop', 'Stop', 'stop', 'danger')),
        ],
    )['ts']
    folder = f'req-{ch}-{p["ts"].replace(".", "")}'
    try:  # the conversation around it, read as the owner
        if p['thread_ts']:
            msgs = slack.USER.conversations_replies(channel=ch, ts=p['thread_ts'], limit=60)['messages']
        else:
            msgs = list(
                reversed(
                    slack.USER.conversations_history(channel=ch, latest=p['ts'], inclusive=True, limit=15)['messages']
                )
            )
    except Exception as e:
        log('request context failed:', e)
        msgs = []
    lines, _ = slack.transcript(msgs)
    files = slack.download(p['files'], folder)
    owner = slack.name(OWNER)
    title = f'{who}: {first_sentence(asked, 60)}'
    tid, err = t3.start_thread(
        default_project(), title, prompts.errand(who, how.replace('you', owner), owner, asked, lines, files, folder)
    )
    if not tid:
        COMP.event('failed', f'Could not start errand for {who}', detail=err, ok=False)
        slack.post(dm, head, f":warning: I couldn't start on it: {err}")
        return
    track(p, dm, head, tid, title, folder, link)


def track(p, dm, head, tid, title, folder, link):
    """Follow an errand's chat in the owner's DM thread (also used to adopt a chat started by hand)."""
    new_task(
        dm,
        head,
        tid,
        title,
        folder,
        head,
        slack.note_only(dm, head, tasks.THINKING),
        requester=p['user'],
        source=link,
        source_ch=p['ch'],
        source_im=p['im'],
        source_thread=p['thread_ts'] or (None if p['im'] else p['ts']),
    )
    log('errand started for', p['user'], tid)
    COMP.event('started', title, task=key(dm, head), detail=f'errand for {slack.name(p["user"])}')


def close_head(task, line, emoji):
    """An errand ended: its head message loses the Stop button, the 👀 becomes `emoji`, and the 'Working on it'
    line becomes `line`, so the DM list shows at a glance what is done."""
    if not task.get('requester'):
        return
    ch, ts = task['channel'], task['thread_ts']
    try:
        m = slack.app.client.conversations_history(channel=ch, latest=ts, oldest=ts, inclusive=True, limit=1)[
            'messages'
        ][0]
    except Exception as e:
        log('close head: message not found', e)
        return

    def swap(x):  # the 👀 in markdown text or in rich_text emoji elements
        if isinstance(x, dict):
            if x.get('type') == 'emoji' and x.get('name') == 'eyes':
                x['name'] = emoji
            for k, v in x.items():
                if k == 'text' and isinstance(v, str):
                    x[k] = v.replace(':eyes:', f':{emoji}:')
                else:
                    swap(v)
        elif isinstance(x, list):
            for v in x:
                swap(v)

    b = [x for x in m.get('blocks', []) if x.get('type') not in ('actions', 'context')]
    swap(b)
    b.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': line}]})
    try:
        slack.app.client.chat_update(channel=ch, ts=ts, text=m.get('text', ''), blocks=b)
        task['closed'] = line
    except Exception as e:
        log('close head failed:', e)


# ---------------------------------------------------------------- approvals
def _approval_blocks(md, note, task_key='', buttons=True):
    b = slack.blocks(md, note)
    if buttons:
        b.append(
            slack.buttons(
                ('errand_approve', 'Approve', task_key, 'primary'), ('errand_reject', 'Reject', task_key, None)
            )
        )
    return b


def ask_approval(task, a):
    """approval.json from the agent -> a DM with Approve / Reject (a new message, so it notifies)."""
    who = slack.name(task.get('requester') or OWNER)
    k = key(task['channel'], task['thread_ts'])
    md = f':raised_hand: **Approve?** {a.get("action", "")}\n\n{a.get("details", "")}' + (
        f'\n\n**Then reply to {who}:**\n' + quote(a['reply']) if a.get('reply') else ''
    )
    ts = slack.app.client.chat_postMessage(
        channel=task['channel'],
        thread_ts=task['thread_ts'],
        text=f'Approve? {first_sentence(str(a.get("action", "")), 150)}',
        blocks=_approval_blocks(md, f'Asked by {who}. Nothing has changed yet.', k),
    )['ts']
    task['approval'] = {
        'action': a.get('action', ''),
        'reply': a.get('reply', ''),
        'ts': ts,
        'md': md,
        'decided': '',
        'files': a.get('files') or [],
    }
    COMP.event('approval', f'Asked you to approve: {a.get("action", "")}'[:200], task=k, detail=f'for {who}')


def decide(task, k, approved):
    a = task.get('approval')
    if not a or a.get('decided'):
        return
    a['decided'] = 'approved' if approved else 'rejected'
    when = datetime.now().strftime('%H:%M')
    slack.app.client.chat_update(
        channel=task['channel'],
        ts=a['ts'],
        text=a['decided'],
        blocks=_approval_blocks(
            a['md'],
            (':white_check_mark: Approved' if approved else ':x: Rejected') + f' by you at {when}',
            buttons=False,
        ),
    )
    who, owner = slack.name(task.get('requester') or OWNER), slack.name(OWNER)
    if approved:
        task['reply_pending'] = a.get('reply') or ''
        msg = f'APPROVED by {owner}: {a["action"]}. Make the change now, check it worked, and confirm in one line.'
    else:
        msg = f'REJECTED by {owner}: do not make this change. Nothing is sent to {who}. Stop here.'
        close_head(task, ':x: Rejected · nothing changed', 'x')
    COMP.event('approved' if approved else 'rejected', f'You {a["decided"]}: {a["action"]}'[:200], task=k)
    save()
    jobs.run_later(tasks.follow_up, task, msg, None, a['ts'])


def stop(task, k):
    res = t3.stop(task['thread'])
    task['reply_pending'] = ''
    COMP.event('stopped', f'You stopped: {task.get("title", "")}', task=k, ok=bool(res.get('ok')))
    if res.get('ok'):
        close_head(task, ':black_square_for_stop: Stopped by you', 'black_square_for_stop')
        slack.post(
            task['channel'],
            task['thread_ts'],
            'Stopped',
            md=':black_square_for_stop: Stopped. Nothing more will be done or sent.',
        )
    else:
        slack.post(
            task['channel'], task['thread_ts'], 'Stopped', md=f":warning: Couldn't stop it: {t3.error_text(res)[:200]}"
        )


# ---------------------------------------------------------------- answering whoever asked
def reply_requester(task, text, files=(), approved=False):
    """Dry run: shown to the owner only, labelled. Otherwise it goes out only after the owner taps Send (or right
    away with approved=True: they already approved this change and saw this reply with it)."""
    who, req = slack.name(task.get('requester') or OWNER), task.get('requester')
    if mode() == 'owner' or not req or req == OWNER:
        slack.post(
            task['channel'],
            task['thread_ts'],
            f'Would send to {who}',
            md=f':outbox_tray: Would send to **{who}**:\n' + quote(text),
            note='Dry run: nothing was sent to them.',
        )
        return
    if approved:
        send_to_requester(task, text, files)
        return
    k = key(task['channel'], task['thread_ts'])
    md = (
        f':outbox_tray: **Send to {who}?**\n'
        + quote(text)
        + (f'\n\nWith {len(files)} file(s), shown above.' if files else '')
    )
    ts = slack.app.client.chat_postMessage(
        channel=task['channel'],
        thread_ts=task['thread_ts'],
        text=f'Send to {who}?',
        blocks=[
            *slack.blocks(md, 'Nothing has been sent yet.'),
            slack.buttons(('reply_send', f'Send to {who}', k, 'primary'), ('reply_skip', "Don't send", k, None)),
        ],
    )['ts']
    task['reply_draft'] = {'text': text, 'files': list(files), 'ts': ts, 'md': md}
    save()


def send_to_requester(task, text, files=()):
    """Deliver as the companion: in their channel thread if the companion can post there, otherwise in a DM. A copy line goes to
    the owner's errand thread."""
    who, req = slack.name(task['requester']), task['requester']
    targets = [] if task.get('source_im') else [(task['source_ch'], task.get('source_thread'))]
    for target, tts in [*targets, ('dm', None)]:
        ch = target
        try:
            if target == 'dm':
                ch = slack.app.client.conversations_open(users=req)['channel']['id']
            slack.app.client.chat_postMessage(
                channel=ch,
                thread_ts=tts,
                text=first_sentence(text, 200),
                blocks=slack.blocks(text, f"From {slack.name(OWNER)}'s assistant"),
            )
            if files:
                slack.upload(ch, tts, files)
            break
        except Exception as e:
            log('send to requester failed in', ch, e)
    else:
        slack.post(
            task['channel'],
            task['thread_ts'],
            'Could not send',
            md=f":warning: Couldn't reach **{who}**. Nothing was sent.",
        )
        return
    slack.post(
        task['channel'], task['thread_ts'], f'Sent to {who}', md=f':outbox_tray: Sent to **{who}**:\n' + quote(text)
    )
    log('sent to requester', req, len(files), 'files')
    COMP.event(
        'sent',
        f'Message to {who}' + (f' with {len(files)} file{"s" if len(files) != 1 else ""}' if files else ''),
        task=key(task['channel'], task['thread_ts']),
        to=who,
        detail=text,
    )
    close_head(
        task, f':white_check_mark: Done · sent to {who} at {datetime.now().strftime("%H:%M")}', 'white_check_mark'
    )


def decide_reply(task, k, send):
    d = task.pop('reply_draft', None)
    if not d:
        return
    who = slack.name(task['requester'])
    slack.app.client.chat_update(
        channel=task['channel'],
        ts=d['ts'],
        text='sent' if send else 'not sent',
        blocks=slack.blocks(
            d['md'],
            (f':white_check_mark: Sent to {who}' if send else ':no_entry_sign: Not sent')
            + f' at {datetime.now().strftime("%H:%M")}',
        ),
    )
    if send:
        send_to_requester(task, d['text'], d['files'])
    else:
        close_head(task, f':black_square_for_stop: Closed · nothing sent to {who}', 'black_square_for_stop')
        COMP.event('skipped', f'You chose not to send the reply to {who}', task=k, to=who)
    save()


# ---------------------------------------------------------------- temporary logins
_creds = {}  # task key -> login, in memory only (never saved)


def ask_credential(task, c):
    """A temporary first-login password for the person who asked: the owner sees the login (password hidden)
    and decides; on Send it goes to that person in a private DM, never into a thread."""
    req = task.get('requester')
    if not req or req == OWNER or not c.get('password'):
        slack.post(
            task['channel'],
            task['thread_ts'],
            'Login not sent',
            md=':no_entry: The agent handed over a login, but there is nobody else to send it to. It was discarded.',
        )
        return
    k = key(task['channel'], task['thread_ts'])
    who = slack.name(req)
    c = {f: str(c.get(f) or '')[:300] for f in ('service', 'url', 'username', 'password', 'note')}
    _creds[k] = c
    md = (
        f':key: **Send {who} their {c["service"] or "new"} login?**\n'
        + (f'Sign in: {c["url"]}\n' if c['url'] else '')
        + f'Username: `{c["username"]}`\nPassword: hidden'
        + (f'\n_{c["note"]}_' if c['note'] else '')
    )
    ts = slack.app.client.chat_postMessage(
        channel=task['channel'],
        thread_ts=task['thread_ts'],
        text=f'Send {who} their login?',
        blocks=[
            *slack.blocks(md, f'Goes to {who} in a private DM.'),
            slack.buttons(('cred_send', f'Send login to {who}', k, 'primary'), ('cred_skip', "Don't send", k, None)),
        ],
    )['ts']
    task['cred_ask'] = {'ts': ts, 'md': md}
    COMP.event('approval', f'Asked you to send {who} their {c["service"] or "new"} login', task=k, to=who)
    save()


def decide_credential(task, k, send):
    ask = task.pop('cred_ask', None)
    if not ask:
        return
    c, who = _creds.pop(k, None), slack.name(task['requester'])
    when = datetime.now().strftime('%H:%M')
    if send and not c:
        line = f':warning: {NAME} restarted since, so the password is gone. Ask the agent for a new one.'
    elif send:
        try:
            dm = slack.app.client.conversations_open(users=task['requester'])['channel']['id']
            text = (
                f'Your {c["service"] or "new"} login' + (f' for {c["url"]}' if c['url'] else '') + ':\n'
                f'Username: `{c["username"]}`\nTemporary password: `{c["password"]}`'
                + (f'\n{c["note"]}' if c['note'] else '')
            )
            slack.app.client.chat_postMessage(
                channel=dm,
                text=f'Your {c["service"] or "new"} login',
                blocks=slack.blocks(text, f"From {slack.name(OWNER)}'s assistant"),
            )
            line = f':white_check_mark: Sent to {who} in a private DM at {when}'
            log('credential sent to', task['requester'])
            COMP.event(
                'sent',
                f'{c["service"] or "New"} login to {who} (private DM)',
                task=k,
                to=who,
                detail=f'username {c["username"]}; password not logged',
            )
        except Exception as e:
            line = f":warning: Couldn't DM {who}: {e}"[:200]
    else:
        line = f':no_entry_sign: Not sent at {when}'
    slack.app.client.chat_update(channel=task['channel'], ts=ask['ts'], text=line, blocks=slack.blocks(ask['md'], line))
    save()


# ---------------------------------------------------------------- buttons (owner only)
def owner_action(handler, locked=True):
    """Wrap a button handler: acknowledge, ignore anyone but the owner, find the task from the button's value
    (or the message it sits on), run under the state lock unless it waits on T3 (Stop)."""

    def run(ack, body):
        ack()
        if body['user']['id'] != OWNER:
            return
        k = body['actions'][0].get('value') or ''
        if k not in state['tasks']:  # the Stop button sits on the head message itself
            k = key(body['channel']['id'], body['message']['ts'])
        task = state['tasks'].get(k)
        if not task:
            return
        if locked:
            with lock:
                handler(task, k)
        else:
            handler(task, k)

    return run


slack.app.action('errand_approve')(owner_action(lambda t, k: decide(t, k, True)))
slack.app.action('errand_reject')(owner_action(lambda t, k: decide(t, k, False)))
slack.app.action('errand_stop')(owner_action(stop, locked=False))
slack.app.action('reply_send')(owner_action(lambda t, k: decide_reply(t, k, True)))
slack.app.action('reply_skip')(owner_action(lambda t, k: decide_reply(t, k, False)))
slack.app.action('cred_send')(owner_action(lambda t, k: decide_credential(t, k, True)))
slack.app.action('cred_skip')(owner_action(lambda t, k: decide_credential(t, k, False)))
