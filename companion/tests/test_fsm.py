"""Every lifecycle is an explicit machine: named states, listed moves, anything else refused (bot/fsm.py)."""

import pytest
from bot import machine, reviews, state
from bot.fsm import ASK, DRAFT, POLL, IllegalStateError, Machine
from conftest import ROUTE


def test_a_move_the_machine_does_not_list_is_refused():
    d = {}
    DRAFT.start(d, 'pending')
    DRAFT.move(d, 'posted')
    with pytest.raises(IllegalStateError):
        DRAFT.move(d, 'discarded')  # a posted update is not thrown away
    with pytest.raises(IllegalStateError):
        ASK.of({'status': 'maybe'})
    with pytest.raises(IllegalStateError):
        POLL.start({}, 'paused')
    with pytest.raises(IllegalStateError):
        Machine('broken', {'a': ('b',)})  # a move to a state it never names


def test_a_draft_goes_round_posted_revising_editing_and_back():
    d = {}
    DRAFT.start(d, 'pending')
    for to in ('posted', 'revising', 'editing', 'posted'):
        DRAFT.move(d, to)
    assert d['status'] == 'posted' and not DRAFT.can(d, 'editing')


def test_records_saved_before_their_machines_are_converted_once():
    state.state['polls']['p'] = {'id': 'p', 'open': False, 'closed': 5.0}
    state.state['drafts']['d'] = {'status': 'posted', 'revising': True}
    state.prepare_for_start()
    assert state.state['polls']['p'] == {'id': 'p', 'state': 'closed', 'closed': 5.0}
    assert state.state['drafts']['d'] == {'status': 'revising'}
    state.state['drafts'].clear()


def test_an_answered_question_moves_the_phase_at_once():
    t = state.new_task('C1', '9.1', 'T9', 'x', 'f9', '9.1', None, ROUTE)
    machine.begin_turn(t, 'owner', 'thread')
    machine.set_asking(t, True)
    assert t['phase'] == 'waiting_answer'
    machine.retake_turn(t, 'owner', 'thread')  # a message mid-turn: before, the phase stayed waiting_answer
    machine.set_asking(t, False)
    assert t['phase'] == 'working'


def test_only_a_running_turn_pauses_and_the_pause_is_the_phase():
    t = state.new_task('C1', '9.2', 'T9', 'x', 'f9', '9.2', None, ROUTE)
    with pytest.raises(IllegalStateError):
        machine.pause(t, 1.0, None, 'run')
    machine.begin_turn(t, 'owner', 'thread')
    machine.pause(t, 1.0, 99.0, 'run')
    assert t['phase'] == 'paused' and machine.paused(t)['resumes_at'] == 99.0
    assert machine.unpause(t) and t['phase'] == 'working' and not machine.unpause(t)


def test_old_review_entries_and_retries_read_as_the_states_they_meant():
    entries = [{'verdict': 'asked'}, {'waiting': True, 'task': 'k'}, {'paused': 0, 'task': 'k'}, {'task': 'k'}, {}]
    for e in entries:
        reviews._upgrade(e)
    assert [e['state'] for e in entries] == ['asked', 'waiting', 'paused', 'reviewing', 'queued']
    assert 'verdict' not in entries[0] and 'waiting' not in entries[1]
    t = state.new_task('C1', '9.3', 'T9', 'x', 'f9', '9.3', None, ROUTE, retries=2, retry_at=50.0)
    state.prepare_for_start()
    assert t['retry'] == {'state': 'waiting', 'count': 2, 'at': 50.0} and 'retries' not in t
