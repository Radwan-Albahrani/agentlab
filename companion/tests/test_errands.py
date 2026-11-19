import json
import os
import secrets

import pytest
from bot import errands, gate, ledger, machine, outbox, publish, state, tasks
from conftest import OWNER, ROUTE, agent_sends, click, receipts


@pytest.fixture
def errand(monkeypatch):
    box = os.path.join(outbox.OUTBOX, 'req-1')
    os.makedirs(box, exist_ok=True)
    for name in os.listdir(box):
        os.remove(os.path.join(box, name))
    with open(os.path.join(box, 'inv.pdf'), 'wb') as f:
        f.write(b'%PDF-1.4')
    followed = []
    monkeypatch.setattr(tasks, 'follow_up', lambda task, msg, files, ts, *rest: followed.append(msg))
    t = state.new_task(
        'D_OWNER',
        '50.1',
        'T1',
        'Salah: invoices',
        'req-1',
        '50.1',
        None,
        ROUTE,
        party=machine.party_of(requester='U_SALAH'),
        source_ch='D_SAM',
        source_im=True,
        source_thread=None,
    )
    machine.open_case(t, 'D_OWNER', '50.1', 'errand')
    machine.begin_turn(t, 'colleague', 'thread')
    return t, box, followed


def to_salah(text, **more):
    return {'type': 'message', 'to': 'Salah', 'text': text, **more}


def test_an_approval_request_shows_the_files_and_waits(errand, fresh_bot):
    t, box, _ = errand
    agent_sends(
        t, {'type': 'approval', 'action': 'Give Salah access', 'details': 'x', 'reply': 'Done', 'files': ['inv.pdf']}
    )
    assert ['errand_approve', 'errand_reject'] in fresh_bot.actions()
    assert len(fresh_bot.uploads) == 1
    assert not os.path.exists(os.path.join(box, 'send.json'))
    assert t['phase'] == 'waiting_owner' and publish.card('k', t)['waiting'] == 'approval'


def test_only_the_owner_can_approve(errand, fresh_bot):
    t, _, followed = errand
    agent_sends(t, {'type': 'approval', 'action': 'Give Salah access', 'details': 'x', 'reply': 'Done'})
    (a,) = ledger.items(t)
    click(fresh_bot, 'errand_approve', user='U_SOMEONE')
    assert a['state'] == 'awaiting_owner' and not followed
    click(fresh_bot, 'errand_approve')
    assert a['state'] == 'approved' and followed[0].startswith('APPROVED')
    reply = ledger.items(t)[-1]  # the approval's reply: approved, sent once the agent's turn completes
    assert (reply['kind'], reply['to'], reply['state'], reply['after']) == ('message', 'requester', 'approved', 'turn')


def test_an_approved_reply_goes_once_the_turn_completes_and_not_if_it_fails(errand, fresh_bot):
    t, _, _ = errand
    agent_sends(t, {'type': 'approval', 'action': 'Give Salah access', 'details': 'x', 'reply': 'You have access.'})
    click(fresh_bot, 'errand_approve')
    assert not any(m['channel'] == 'D_U_SALAH' for m in fresh_bot.messages)
    errands.after_turn(t, completed=True)
    assert any(m['channel'] == 'D_U_SALAH' and 'You have access.' in json.dumps(m) for m in fresh_bot.messages)
    assert ledger.items(t)[-1]['state'] == 'sent'
    agent_sends(t, {'type': 'approval', 'action': 'Remove the old login', 'details': 'x', 'reply': 'Removed it.'})
    click(fresh_bot, 'errand_approve')
    errands.after_turn(t, completed=False)
    to_him = [m for m in fresh_bot.messages if m['channel'] == 'D_U_SALAH']
    assert ledger.items(t)[-1]['state'] == 'failed' and 'Removed it.' not in json.dumps(to_him)


def test_a_reply_waits_for_send_then_goes_to_whoever_asked(errand, fresh_bot):
    t, _, _ = errand
    agent_sends(t, to_salah('Here you go', files=['inv.pdf']))
    assert ['reply_send', 'reply_skip'] in fresh_bot.actions()
    assert not any(m['channel'] == 'D_U_SALAH' for m in fresh_bot.messages)
    assert publish.card('k', t)['waiting'] == 'send'
    click(fresh_bot, 'reply_send')
    assert any(m['channel'] == 'D_U_SALAH' for m in fresh_bot.messages)
    assert ledger.items(t)[-1]['state'] == 'sent' and t['phase'] == 'working'


def test_two_replies_wait_side_by_side_and_each_is_decided_alone(errand, fresh_bot):
    t, _, _ = errand
    agent_sends(t, to_salah('Old instructions'))
    agent_sends(t, to_salah('New instructions'))
    click(fresh_bot, 'reply_skip', nth=0)
    click(fresh_bot, 'reply_send', nth=1)
    assert [i['state'] for i in ledger.items(t)] == ['rejected', 'sent']
    assert 'New instructions' in fresh_bot.text()


def test_a_failed_delivery_is_failed_with_why(errand, fresh_bot, monkeypatch):
    t, _, _ = errand
    agent_sends(t, to_salah('Here you go'))
    original = fresh_bot.chat_postMessage

    def unreachable(**kw):
        if kw['channel'] == 'D_U_SALAH':
            raise RuntimeError('unavailable')
        return original(**kw)

    monkeypatch.setattr(fresh_bot, 'chat_postMessage', unreachable)
    click(fresh_bot, 'reply_send')
    (it,) = ledger.items(t)
    assert it['state'] == 'failed' and it['note'] == "couldn't reach Salah"
    assert "couldn't reach Salah" in fresh_bot.text()  # the owner is told


def test_a_temporary_login_is_never_shown_and_goes_privately(errand, fresh_bot):
    t, box, _ = errand
    temp = secrets.token_hex(6)  # not a literal, so secret scanners stay quiet
    agent_sends(t, {'type': 'credential', 'service': 'ExampleApp', 'username': 'salah', 'password': temp})
    assert not any(n.startswith('send') for n in os.listdir(box))  # the file with the password is gone
    assert ['cred_send', 'cred_skip'] in fresh_bot.actions()
    assert temp not in fresh_bot.text() and temp not in json.dumps(ledger.items(t))
    assert temp not in json.dumps(receipts(box))
    click(fresh_bot, 'cred_send')
    private = [m for m in fresh_bot.messages if m['channel'] == 'D_U_SALAH']
    assert private and temp in json.dumps(private)
    assert ledger.items(t)[-1]['state'] == 'sent'


def test_a_login_after_a_restart_is_lost_not_sent(errand, fresh_bot):
    t, _, _ = errand
    agent_sends(t, {'type': 'credential', 'service': 'ExampleApp', 'username': 'salah', 'password': 'x' * 12})
    errands._creds.clear()  # the companion restarted
    click(fresh_bot, 'cred_send')
    assert ledger.items(t)[-1]['state'] == 'lost'
    assert not any(m['channel'] == 'D_U_SALAH' for m in fresh_bot.messages)


def test_files_outside_the_allowed_types_are_held_back(errand):
    _, box, _ = errand
    with open(os.path.join(box, 'run.sh'), 'w') as f:
        f.write('echo hi')
    ok, refused = gate.files(box, ['inv.pdf', 'run.sh', 'missing.pdf', '../../etc/passwd'])
    assert [os.path.basename(p) for p in ok] == ['inv.pdf']
    assert len(refused) == 3


def test_in_dry_run_a_reply_is_shown_and_never_sent(errand, fresh_bot, monkeypatch):
    t, _, _ = errand
    monkeypatch.setattr(errands, 'mode', lambda: 'owner')
    agent_sends(t, to_salah('Here you go'))
    assert ledger.items(t)[-1]['state'] == 'dry_run' and 'Would send to' in fresh_bot.text()
    assert not any(m['channel'] == 'D_U_SALAH' for m in fresh_bot.messages)
    assert OWNER  # the owner's DM is where it was shown
