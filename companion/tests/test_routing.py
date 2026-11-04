import pytest
from bot import requests, routing, slack, tasks
from bot.state import state
from conftest import OWNER


@pytest.fixture
def started(monkeypatch):
    calls = []
    monkeypatch.setattr(requests, 'owner_tagged', lambda ev: calls.append(('errand', ev['ts'])))
    monkeypatch.setattr(tasks, 'start', lambda ch, tts, ts, text, elsewhere=None: calls.append(('task', ts, elsewhere)))
    return calls


def tag(ts, text, user=OWNER, channel='C1', thread='100.1'):
    return {'channel': channel, 'thread_ts': thread, 'ts': ts, 'user': user, 'text': text}


def test_bare_tag_under_someone_elses_message_is_an_errand(started):
    routing.route(tag('101.1', '<@BCOMPANION>'), True)
    assert started == [('errand', '101.1')]


def test_tag_with_instructions_is_a_task_in_that_thread(started):
    routing.route(tag('102.1', '<@BCOMPANION> fix the duplicate rewards'), True)
    assert started == [('task', '102.1', None)]


def test_each_message_is_handled_once(started):
    routing.route(tag('103.1', '<@BCOMPANION>'), True)
    routing.route(tag('103.1', '<@BCOMPANION>'), True)
    assert len(started) == 1


def test_a_colleague_tagging_the_owner_is_ignored_in_restricted_mode(started):
    routing.route({'channel': 'C1', 'ts': '104.1', 'user': 'U_SALAH', 'text': f'<@{OWNER}> send the invoices?'}, False)
    assert not started
    assert not requests._pending


def test_anyone_else_addressing_companion_gets_one_refusal(fresh_bot, started):
    routing.route(tag('105.1', '<@BCOMPANION> hi', user='U_SALAH', thread=None), True)
    routing.route(tag('105.2', '<@BCOMPANION> hello?', user='U_SALAH', thread='105.1'), True)
    assert not started
    assert len(fresh_bot.messages) == 1
    assert 'I only take tasks from' in fresh_bot.messages[0]['text']


def test_a_dm_to_companion_starts_a_task(started):
    routing.route({'channel': 'D_OWNER', 'ts': '106.1', 'user': OWNER, 'text': 'check the queue'}, False)
    assert started == [('task', '106.1', None)]


def test_a_tag_in_a_channel_companion_isnt_in_waits_for_the_invite(monkeypatch, started):
    monkeypatch.setattr('bot.slack.bot_in', lambda ch: False)
    routing.route({'channel': 'C9', 'ts': '107.1', 'user': OWNER, 'text': '<@BCOMPANION> look at this'}, True)
    assert not started
    assert '107.1' in state['awaiting_invite']


def in_his_dm(ts, text):
    return {'channel': 'D_SALAH', 'channel_type': 'im', 'ts': ts, 'user': OWNER, 'text': text}


def test_a_bare_tag_in_his_dm_is_an_errand(started):
    routing.route(in_his_dm('108.1', '<@BCOMPANION>'), True)
    assert started == [('errand', '108.1')]


def test_a_tag_with_instructions_in_his_dm_is_a_task_in_his_companion_dm(fresh_bot, monkeypatch, started):
    monkeypatch.setattr(
        slack.USER,
        'conversations_history',
        lambda **kw: {'messages': [{'user': OWNER, 'ts': '109.1', 'text': '<@BCOMPANION> check his login'}, *THEIRS]},
    )
    monkeypatch.setattr(
        slack.USER, 'conversations_info', lambda channel: {'channel': {'is_im': True, 'user': 'U_SALAH'}}
    )
    routing.route(in_his_dm('109.1', '<@BCOMPANION> check his login'), True)
    ((kind, head, (where, msgs)),) = started
    assert kind == 'task'
    assert fresh_bot.messages[0]['channel'] == 'D_OWNER'
    assert head == '1.0'
    assert where == 'their Slack DM with Salah'
    assert [m['ts'] for m in msgs] == ['108.9', '109.1']


THEIRS = [{'user': 'U_SALAH', 'ts': '108.9', 'text': 'I cannot log in'}]
