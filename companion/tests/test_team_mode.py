import json

import pytest
from bot import errands, requests, routing, t3
from conftest import OWNER, set_settings


@pytest.fixture
def team(monkeypatch):
    set_settings({'mode': 'team'})
    started = []
    monkeypatch.setattr(errands, 'start', lambda p, what='': started.append(what))
    return started


def ask(monkeypatch, verdict, ts='200.1'):
    monkeypatch.setattr(t3, 'triage', lambda prompt: verdict)
    routing.route({'channel': 'C2', 'ts': ts, 'user': 'U_SALAH', 'text': f'<@{OWNER}> can you help?'}, False)
    for p in requests._pending.values():
        p['last'] = 0  # skip REQ_SETTLE
    requests.pending_tick()


def test_a_clear_small_request_starts_an_errand(monkeypatch, team, fresh_bot):
    ask(monkeypatch, {'ok': True, 'result': json.dumps({'kind': 'errand', 'what': 'send the invoices'})})
    assert team == ['send the invoices']


def test_real_work_gets_a_heads_up_in_the_owners_dm(monkeypatch, team, fresh_bot):
    ask(monkeypatch, {'ok': True, 'result': json.dumps({'kind': 'task', 'what': 'fix the dashboard'})})
    assert not team
    assert any('asked you' in m['text'] and m['channel'] == 'D_OWNER' for m in fresh_bot.messages)


def test_small_talk_is_ignored(monkeypatch, team, fresh_bot):
    ask(monkeypatch, {'ok': True, 'result': json.dumps({'kind': 'nothing', 'what': 'thanks'})})
    assert not team
    assert not fresh_bot.messages


def test_broken_triage_tells_the_owner_instead_of_dropping_it(monkeypatch, team, fresh_bot):
    ask(monkeypatch, {'ok': False, 'error': 'down'})
    assert "Couldn't check" in fresh_bot.text()


def test_the_owners_own_bare_tag_still_runs_as_an_errand(monkeypatch, team):
    tagged = []
    monkeypatch.setattr(requests, 'owner_tagged', lambda ev: tagged.append(ev['ts']))
    routing.route({'channel': 'C1', 'thread_ts': '100.1', 'ts': '300.1', 'user': OWNER, 'text': '<@BCOMPANION>'}, True)
    assert tagged == ['300.1']
