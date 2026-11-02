"""Following a T3 chat: a turn finishing, busy-model retries, errands that need nothing, "status?" questions."""

import pytest
from bot import state, t3, tasks
from conftest import set_settings


def task(**extra):
    now = state.now_iso()
    t = {
        'thread': 'T1',
        'title': 'Check the queue',
        'project': '/workspace/platform',
        'channel': 'C9',
        'thread_ts': '9.1',
        'outbox': 'x',
        'trigger_ts': '9.1',
        'status_ts': 'ts9',
        'active': True,
        'start': now,
        'burst_start': now,
        'seen': '',
        'step_from': '',
        'asked': [],
        'prs': [],
        'workers_said': 0,
        'last_status': '',
        'last_status_at': 0,
        'quiet_since': 0,
        'options': {},
        **extra,
    }
    state.state['tasks'][state.key(t['channel'], t['thread_ts'])] = t
    return t


def snapshot(status, answer=None):
    messages = [('m1', state.now_iso(), answer)] if answer else []
    return lambda tid, since: {
        'running': False,
        'last_status': status,
        'last_done': state.now_iso(),
        'messages': messages,
        'requests': [],
        'workers': [],
        'prs': [],
    }


def test_a_finished_turn_posts_the_answer(monkeypatch, t3_quiet, fresh_bot):
    monkeypatch.setattr(t3, 'snapshot', snapshot('completed', 'The queue is empty.'))
    t = task()
    tasks.tick(t)
    assert not t['active'] and t['outcome'] == 'answered'
    assert 'queue is empty' in fresh_bot.text()


def test_a_busy_model_gets_an_automatic_continue(monkeypatch, t3_quiet):
    monkeypatch.setattr(t3, 'snapshot', snapshot('failed'))
    monkeypatch.setattr(t3, 'run_error', lambda tid: '{"message": "Selected model is at capacity"}')
    t = task()
    tasks.tick(t)
    assert t['active'] and t['retry_at'] and t['retries'] == 1


def test_with_auto_retry_off_the_failure_is_reported(monkeypatch, t3_quiet):
    set_settings({'auto_retry': False})
    monkeypatch.setattr(t3, 'snapshot', snapshot('failed'))
    monkeypatch.setattr(t3, 'run_error', lambda tid: '{"message": "Selected model is at capacity"}')
    t = task()
    tasks.tick(t)
    assert not t['active'] and t['outcome'] == 'failed'


def test_an_errand_that_needs_nothing_closes_quietly(monkeypatch, t3_quiet, fresh_bot):
    monkeypatch.setattr(t3, 'snapshot', snapshot('completed', 'NO_ACTION: only Sam can decide this'))
    t = task(requester='U_SALAH', channel='D_OWNER')
    tasks.tick(t)
    assert t['outcome'] == 'nothing needed'
    assert t['closed'].endswith('Nothing needed')
    assert not fresh_bot.messages  # no answer posted, just the lines edited


@pytest.mark.parametrize(
    'message, is_status',
    [
        ('status?', True),
        ("how's it going", True),
        ('any update?', True),
        ('fix the status badge', False),
        ('check the status page and update the docs please now', False),
    ],
)
def test_status_questions_are_told_apart_from_instructions(message, is_status):
    assert tasks.is_status_ask(message) is is_status
