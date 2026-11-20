"""Errands: work done as the owner for someone who asked them, run from a thread in the owner's DM; owner-only buttons."""

from collections.abc import Callable, Sequence

from slack_bolt import Ack

from . import cases, gate, jobs, ledger, machine, projects, prompts, slack, t3, tasks
from .config import COMP, NAME, OWNER, log, mode
from .shapes import Item, Request, Route, Task
from .slack import Json
from .state import key, key_of, lock, new_task, save, state
from .text import first_sentence, quote
from .when import say


def start(p: Request, what: str = '') -> None:
    """p: the request: ch, ts, thread_ts, user (who asked), im, texts, files, tagged."""
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
            *(slack.blocks(md, 'Working on it. Sensitive changes wait for your approval here.') or []),
            slack.buttons(('errand_stop', 'Stop', 'stop', 'danger')),
        ],
    )['ts']
    folder = f'req-{ch}-{p["ts"].replace(".", "")}'
    try:
        if p['thread_ts']:
            msgs = slack.owner_client().conversations_replies(channel=ch, ts=p['thread_ts'], limit=60)['messages']
        else:
            msgs = list(
                reversed(
                    slack.owner_client().conversations_history(channel=ch, latest=p['ts'], inclusive=True, limit=15)[
                        'messages'
                    ]
                )
            )
    except Exception as e:
        log('request context failed:', e)
        msgs = []
    lines, _ = slack.transcript(msgs)
    files = slack.download(p['files'], folder)
    owner = slack.name(OWNER)
    title = f'{who}: {first_sentence(asked, 60)}'
    where_to = projects.route('errand')
    tid, err = t3.start_thread(
        where_to['project'], title, prompts.errand(who, how.replace('you', owner), owner, asked, lines, files, folder)
    )
    if not tid:
        COMP.event('failed', f'Could not start errand for {who}', detail=err, ok=False)
        slack.post(dm, head, f":warning: I couldn't start on it: {err}")
        return
    track(p, dm, head, tid, title, folder, link, where_to)


def track(p: Request, dm: str, head: str, tid: str, title: str, folder: str, link: str, where_to: Route) -> None:
    """Register an errand's chat as a task in the owner's DM thread."""
    task = new_task(
        dm,
        head,
        tid,
        title,
        folder,
        head,
        tasks.post_line(dm, head, tasks.THINKING),
        where_to,
        party=machine.party_of(requester=p['user']),
        audit=tasks.audit(
            OWNER if p.get('tagged') else p['user'],
            'by your tag on their message' if p.get('tagged') else 'noticed in team mode',
            for_=p['user'],
        ),
        source=link,
        source_ch=p['ch'],
        source_im=p['im'],
        source_thread=p['thread_ts'] or (None if p['im'] else p['ts']),
    )
    machine.open_case(task, dm, head, 'errand')  # the errand's thread is the owner's: it is the case
    machine.begin_turn(task, 'colleague', 'thread')
    cases.heard(task, p['user'], '\n'.join(p['texts']), p.get('files'), first=True)
    log('errand started for', p['user'], tid)
    COMP.event('started', title, task=key(dm, head), detail=f'errand for {slack.name(p["user"])}')


def close_head(task: Task, line: str, emoji: str) -> None:
    """Mark the errand's head message ended: no Stop button, :eyes: -> `emoji`, footer -> `line`."""
    if machine.party(task)['kind'] != 'errand':
        return
    ch, ts = task['channel'], task['thread_ts']
    try:
        m = slack.app.client.conversations_history(channel=ch, latest=ts, oldest=ts, inclusive=True, limit=1)[
            'messages'
        ][0]
    except Exception as e:
        log('close head: message not found', e)
        return

    def swap(x: object) -> None:
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


def _approval_blocks(md: str, note: str, task_key: str = '', buttons: bool = True) -> list[Json]:
    b = slack.blocks(md, note) or []
    if buttons:
        b.append(
            slack.buttons(
                ('errand_approve', 'Approve', task_key, 'primary'), ('errand_reject', 'Reject', task_key, None)
            )
        )
    return b


def approver(task: Task) -> tuple[str, str]:
    """Where the owner decides: the case thread, else the task's own thread."""
    return cases.owner_place(task)


def _close_card(it: Item, line: str) -> None:
    """Take the buttons off a card, with `line` saying why."""
    slack.app.client.chat_update(
        channel=it['card']['ch'], ts=it['card']['ts'], text=line, blocks=_approval_blocks(it['md'], line, buttons=False)
    )


def ask_approval(task: Task, it: Item, box: str | None = None) -> None:
    """A ledger approval -> owner-only Approve / Reject where the owner follows the task. It replaces any approval
    still waiting; the files it would send are shown with it."""
    who = cases.who(task)
    k = key_of(task)
    for old in ledger.pending(task, 'approval'):
        _close_card(old, ':arrows_counterclockwise: Replaced by a newer request below')
        ledger.move(task, old, 'replaced', note=f'replaced by a newer request: {it["action"]}'[:300])
    link = slack.permalink(task['channel'], task['thread_ts']) if machine.is_colleague(task) else ''
    md = (
        f':raised_hand: **Approve?** {it["action"]}\n\n{it.get("details", "")}'
        + (f'\n\n**Then reply to {who}:**\n' + quote(it['reply']) if it.get('reply') else '')
        + (f"\n\n<{link}|Open {who}'s thread>" if link else '')
    )
    ch, tts = approver(task)
    ts = slack.app.client.chat_postMessage(
        channel=ch,
        thread_ts=tts,
        text=f'Approve? {first_sentence(str(it["action"]), 150)}',
        blocks=_approval_blocks(md, f'Asked by {who}. Nothing has changed yet.', k),
    )['ts']
    ledger.move(task, it, 'awaiting_owner', card={'ch': ch, 'ts': ts}, md=md)
    if box and it.get('files'):
        ok, refused = gate.files(box, it['files'])
        if ok:
            slack.upload(
                ch,
                tts,
                ok,
                f':mag: Preview: {len(ok)} file{"s" if len(ok) != 1 else ""} that will go out if you approve'
                + (f' ({len(refused)} would be held back: {", ".join(refused)})' if refused else ''),
            )
    COMP.event('approval', f'Asked you to approve: {it["action"]}'[:200], task=k, detail=f'for {who}')


def withdraw(task: Task, why: str) -> None:
    """The agent takes back the approval waiting (it learned more, or was told to hold)."""
    waiting = ledger.pending(task, 'approval')
    if not waiting:
        log('withdraw: no approval is waiting', key_of(task))
        return
    it = waiting[-1]
    _close_card(it, f':leftwards_arrow_with_hook: Withdrawn by {NAME}: {why or "no reason given"}')
    ledger.move(task, it, 'withdrawn', note=why)
    COMP.event('withdrawn', f'Withdrew the approval request: {it["action"]}'[:200], task=key_of(task), detail=why)


def decide(task: Task, k: str, approved: bool, card: str) -> None:
    """The owner's Approve / Reject on `card`; a card no longer waiting (replaced, withdrawn, decided) decides
    nothing."""
    it = ledger.on_card(task, card)
    if not it or it['kind'] != 'approval' or it['state'] != 'awaiting_owner':
        return
    when = say()
    slack.app.client.chat_update(
        channel=it['card']['ch'],
        ts=card,
        text='approved' if approved else 'rejected',
        blocks=_approval_blocks(
            it['md'],
            (':white_check_mark: Approved' if approved else ':x: Rejected') + f' by you at {when}',
            buttons=False,
        ),
    )
    ledger.move(task, it, 'approved' if approved else 'rejected')
    who, owner = cases.who(task), slack.name(OWNER)
    if approved:
        if it.get('reply') and machine.party(task)['kind'] == 'errand':  # sent once the agent has made the change
            r = ledger.add(task, 'message', to='requester', label=who, text=it['reply'], after='turn', ref=it['id'])
            ledger.move(task, r, 'approved', note=f'with approval {it["id"]}')
        msg = f'APPROVED by {owner}: {it["action"]}. Make the change now, check it worked, and confirm in one line.'
    else:
        msg = f'REJECTED by {owner}: do not make this change. Nothing is sent to {who}. Stop here.'
        close_head(task, ':x: Rejected · nothing changed', 'x')
    COMP.event('approved' if approved else 'rejected', f'You {it["state"]}: {it["action"]}'[:200], task=k)
    save()
    jobs.run_later(tasks.follow_up, task, msg, None, card, 'thread', None, True)


def after_turn(task: Task, completed: bool) -> None:
    """Messages approved to go once the turn is over: sent if it completed, else failed."""
    for it in ledger.items(task):
        if it['kind'] == 'message' and it['state'] == 'approved' and it.get('after') == 'turn':
            if completed:
                send_to_requester(task, it, it.get('paths') or [])
            else:
                ledger.move(task, it, 'failed', note='the turn did not complete')


def stop(task: Task, k: str) -> None:
    res = t3.stop(task['thread'])
    after_turn(task, completed=False)
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


def offer_reply(task: Task, it: Item, ok: Sequence[str] = (), refused: Sequence[str] = ()) -> None:
    """A ledger message for an errand's requester: Send / Don't send for the owner (sent at once when it answers a
    decision the owner just approved; never sent in dry run)."""
    who = cases.who(task)
    it['paths'] = list(ok)
    if refused:
        it['held'] = ', '.join(refused)
    if mode() == 'owner':
        slack.post(
            task['channel'],
            task['thread_ts'],
            f'Would send to {who}',
            md=f':outbox_tray: Would send to **{who}**:\n' + quote(it['text']),
            note='Dry run: nothing was sent to them.',
        )
        ledger.move(task, it, 'dry_run')
        return
    turn = machine.turn(task)
    approval = ledger.latest(task, 'approval', {'approved'})
    if turn.get('by') == 'decision' and approval and approval['updated'] >= turn.get('at', 0) - 5:
        ledger.move(task, it, 'approved', note=f'with approval {approval["id"]}')
        send_to_requester(task, it, ok)
        return
    md = (
        f':outbox_tray: **Send to {who}?**\n'
        + quote(it['text'])
        + (f'\n\nWith {len(ok)} file(s), shown above.' if ok else '')
    )
    if ok:
        slack.upload(task['channel'], task['thread_ts'], ok, f':mag: The file(s) that would go to {who}')
    ts = slack.app.client.chat_postMessage(
        channel=task['channel'],
        thread_ts=task['thread_ts'],
        text=f'Send to {who}?',
        blocks=[
            *(slack.blocks(md, 'Nothing has been sent yet.') or []),
            slack.buttons(
                ('reply_send', f'Send to {who}', key_of(task), 'primary'),
                ('reply_skip', "Don't send", key_of(task), None),
            ),
        ],
    )['ts']
    ledger.move(task, it, 'awaiting_owner', card={'ch': task['channel'], 'ts': ts}, md=md)


def send_to_requester(task: Task, it: Item, files: Sequence[str] = ()) -> None:
    """Send the reply in the requester's thread if possible, else by DM; sent or failed."""
    who, req = cases.who(task), machine.party(task)['user']
    targets: list[tuple[str, str | None]] = (
        [] if task.get('source_im') else [(task['source_ch'], task.get('source_thread'))]
    )
    for target, tts in [*targets, ('dm', None)]:
        ch = target
        try:
            if target == 'dm':
                ch = slack.app.client.conversations_open(users=req)['channel']['id']
            slack.app.client.chat_postMessage(
                channel=ch,
                thread_ts=tts,
                text=first_sentence(it['text'], 200),
                blocks=slack.blocks(it['text'], f"From {slack.name(OWNER)}'s assistant"),
            )
            if files:
                slack.upload(ch, tts, files)
            break
        except Exception as e:
            log('send to requester failed in', ch, e)
    else:
        ledger.move(task, it, 'failed', note=f"couldn't reach {who}")
        return
    slack.post(
        task['channel'],
        task['thread_ts'],
        f'Sent to {who}',
        md=f':outbox_tray: Sent to **{who}**:\n' + quote(it['text']),
    )
    ledger.move(task, it, 'sent')
    log('sent to requester', req, len(files), 'files')
    COMP.event(
        'sent',
        f'Message to {who}' + (f' with {len(files)} file{"s" if len(files) != 1 else ""}' if files else ''),
        task=key_of(task),
        to=who,
        detail=it['text'],
    )
    close_head(task, f':white_check_mark: Done · sent to {who} at {say()}', 'white_check_mark')


def decide_reply(task: Task, k: str, send: bool, card: str) -> None:
    it = ledger.on_card(task, card)
    if not it or it['state'] != 'awaiting_owner':
        return
    who = cases.who(task)
    slack.app.client.chat_update(
        channel=it['card']['ch'],
        ts=card,
        text='sent' if send else 'not sent',
        blocks=slack.blocks(
            it['md'],
            (f':white_check_mark: Sent to {who}' if send else ':no_entry_sign: Not sent') + f' at {say()}',
        ),
    )
    if send:
        ledger.move(task, it, 'approved')
        send_to_requester(task, it, it.get('paths') or [])
    else:
        ledger.move(task, it, 'rejected')
        close_head(task, f':black_square_for_stop: Closed · nothing sent to {who}', 'black_square_for_stop')
        COMP.event('skipped', f'You chose not to send the reply to {who}', task=k, to=who)


# (task key, item id) -> login; memory only, never persisted, never in the ledger
_creds: dict[tuple[str, str], dict[str, str]] = {}


def ask_credential(task: Task, raw: Json) -> None:
    """Ask the owner whether to DM a temporary password to the person the task is for (never into a thread)."""
    p = machine.party(task)
    c = {f: str(raw.get(f) or '')[:300] for f in ('service', 'url', 'username', 'password', 'note')}
    who = slack.name(p['user'])
    it = ledger.add(
        task, 'credential', to='person', label=who, text=f'{c["service"] or "New"} login for {c["username"] or "?"}'
    )
    if p['kind'] == 'owner' or not c['password']:
        ledger.move(task, it, 'refused', note='there is nobody else to send it to' if c['password'] else 'no password')
        return
    k = key_of(task)
    _creds[(k, it['id'])] = c
    md = (
        f':key: **Send {who} their {c["service"] or "new"} login?**\n'
        + (f'Sign in: {c["url"]}\n' if c['url'] else '')
        + f'Username: `{c["username"]}`\nPassword: hidden'
        + (f'\n_{c["note"]}_' if c['note'] else '')
    )
    ch, tts = cases.owner_place(task)
    ts = slack.app.client.chat_postMessage(
        channel=ch,
        thread_ts=tts,
        text=f'Send {who} their login?',
        blocks=[
            *(slack.blocks(md, f'Goes to {who} in a private DM.') or []),
            slack.buttons(('cred_send', f'Send login to {who}', k, 'primary'), ('cred_skip', "Don't send", k, None)),
        ],
    )['ts']
    ledger.move(task, it, 'awaiting_owner', card={'ch': ch, 'ts': ts}, md=md)
    COMP.event('approval', f'Asked you to send {who} their {c["service"] or "new"} login', task=k, to=who)


def decide_credential(task: Task, k: str, send: bool, card: str) -> None:
    it = ledger.on_card(task, card)
    if not it or it['state'] != 'awaiting_owner':
        return
    c, p = _creds.pop((k, it['id']), None), machine.party(task)
    who = slack.name(p['user'])
    when = say()
    if not send:
        line = f':no_entry_sign: Not sent at {when}'
        ledger.move(task, it, 'rejected')
    elif not c:
        line = f':warning: {NAME} restarted since, so the password is gone. Ask the agent for a new one.'
        ledger.move(task, it, 'lost', note='the companion restarted, so the password is gone')
    else:
        try:
            dm = slack.app.client.conversations_open(users=p['user'])['channel']['id']
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
            ledger.move(task, it, 'sent')
            log('credential sent to', p['user'])
            COMP.event(
                'sent',
                f'{c["service"] or "New"} login to {who} (private DM)',
                task=k,
                to=who,
                detail=f'username {c["username"]}; password not logged',
            )
        except Exception as e:
            line = f":warning: Couldn't DM {who}: {e}"[:200]
            ledger.move(task, it, 'failed', note=str(e)[:200])
    slack.app.client.chat_update(channel=it['card']['ch'], ts=card, text=line, blocks=slack.blocks(it['md'], line))


def owner_action(handler: Callable[..., None], locked: bool = True, card: bool = False) -> Callable[[Ack, Json], None]:
    """Wrap a button handler: ack, owner only, resolve the task, run under the state lock if `locked`; `card`: also
    pass the pressed message's ts."""

    def run(ack: Ack, body: Json) -> None:
        ack()
        if body['user']['id'] != OWNER:
            return
        k = body['actions'][0].get('value') or ''
        if k not in state['tasks']:
            k = key(body['channel']['id'], body['message']['ts'])
        task = state['tasks'].get(k)
        if not task:
            return
        args = (task, k, body['message']['ts']) if card else (task, k)
        if locked:
            with lock:
                handler(*args)
        else:
            handler(*args)

    return run


slack.app.action('errand_approve')(owner_action(lambda t, k, ts: decide(t, k, True, ts), card=True))
slack.app.action('errand_reject')(owner_action(lambda t, k, ts: decide(t, k, False, ts), card=True))
slack.app.action('errand_stop')(owner_action(stop, locked=False))
slack.app.action('reply_send')(owner_action(lambda t, k, ts: decide_reply(t, k, True, ts), card=True))
slack.app.action('reply_skip')(owner_action(lambda t, k, ts: decide_reply(t, k, False, ts), card=True))
slack.app.action('cred_send')(owner_action(lambda t, k, ts: decide_credential(t, k, True, ts), card=True))
slack.app.action('cred_skip')(owner_action(lambda t, k, ts: decide_credential(t, k, False, ts), card=True))
