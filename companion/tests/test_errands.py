"""An errand's outbox: approvals, replies to whoever asked, temporary logins. Only the owner can press a button."""

import json
import os
import secrets

import pytest
from bot import errands, outbox, state, tasks
from conftest import OWNER


@pytest.fixture
def errand(monkeypatch):
    box = os.path.join(outbox.OUTBOX, 'req-1')
    os.makedirs(box, exist_ok=True)
    for name in os.listdir(box):
        os.remove(os.path.join(box, name))
    with open(os.path.join(box, 'inv.pdf'), 'wb') as f:
        f.write(b'%PDF-1.4')
    followed = []
    monkeypatch.setattr(tasks, 'follow_up', lambda task, msg, files, ts: followed.append(msg))
    t = state.new_task(
        'D_OWNER',
        '50.1',
        'T1',
        'Salah: invoices',
        'req-1',
        '50.1',
        None,
        requester='U_SALAH',
        source_ch='D_SAM',
        source_im=True,
        source_thread=None,
    )
    return t, box, followed


def drop(box, name, data):
    with open(os.path.join(box, name), 'w') as f:
        json.dump(data, f)


def press(action, user=OWNER):
    handler = {
        'approve': lambda t, k: errands.decide(t, k, True),
        'send': lambda t, k: errands.decide_reply(t, k, True),
        'send_login': lambda t, k: errands.decide_credential(t, k, True),
    }[action]
    body = {
        'user': {'id': user},
        'actions': [{'value': state.key('D_OWNER', '50.1')}],
        'channel': {'id': 'D_OWNER'},
        'message': {'ts': '50.1'},
    }
    errands.owner_action(handler)(lambda: None, body)


def test_an_approval_request_shows_the_files_and_waits(errand, fresh_bot):
    t, box, _ = errand
    drop(box, 'approval.json', {'action': 'Give Salah access', 'details': 'x', 'reply': 'Done', 'files': ['inv.pdf']})
    outbox.tick(t)
    assert ['errand_approve', 'errand_reject'] in fresh_bot.actions()
    assert len(fresh_bot.uploads) == 1
    assert not os.path.exists(os.path.join(box, 'approval.json'))


def test_only_the_owner_can_approve(errand):
    t, box, followed = errand
    drop(box, 'approval.json', {'action': 'Give Salah access', 'details': 'x', 'reply': 'Done'})
    outbox.tick(t)
    press('approve', user='U_SOMEONE')
    assert not t['approval']['decided'] and not followed
    press('approve')
    assert t['approval']['decided'] == 'approved'
    assert followed[0].startswith('APPROVED')


def test_a_reply_waits_for_send_then_goes_to_whoever_asked(errand, fresh_bot):
    t, box, _ = errand
    drop(box, 'manifest.json', {'for': 'Salah', 'what': 'invoices', 'files': ['inv.pdf'], 'reply': 'Here you go'})
    outbox.tick(t)
    assert ['reply_send', 'reply_skip'] in fresh_bot.actions()
    assert not any(m['channel'] == 'D_U_SALAH' for m in fresh_bot.messages)
    press('send')
    assert any(m['channel'] == 'D_U_SALAH' for m in fresh_bot.messages)


def test_a_temporary_login_is_never_shown_and_goes_privately(errand, fresh_bot):
    t, box, _ = errand
    temp = secrets.token_hex(6)  # made up per run, so no credential-looking literal sits in the repo
    drop(box, 'credential.json', {'for': 'Salah', 'service': 'ExampleApp', 'username': 'salah', 'password': temp})
    outbox.tick(t)
    assert not os.path.exists(os.path.join(box, 'credential.json'))
    assert ['cred_send', 'cred_skip'] in fresh_bot.actions()
    assert temp not in fresh_bot.text()
    press('send_login')
    private = [m for m in fresh_bot.messages if m['channel'] == 'D_U_SALAH']
    assert private and temp in json.dumps(private)


def test_files_outside_the_allowed_types_are_held_back(errand):
    _, box, _ = errand
    with open(os.path.join(box, 'run.sh'), 'w') as f:
        f.write('echo hi')
    ok, refused = outbox.gate(box, ['inv.pdf', 'run.sh', 'missing.pdf', '../../etc/passwd'])
    assert [os.path.basename(p) for p in ok] == ['inv.pdf']
    assert len(refused) == 3
