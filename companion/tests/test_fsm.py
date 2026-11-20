"""Every lifecycle is an explicit machine: named states, listed moves, anything else refused (bot/fsm.py)."""

import pytest
from bot import machine, state
from bot.fsm import ASK, DRAFT, POLL, IllegalStateError, Machine
from conftest import ROUTE


def test_a_move_the_machine_does_not_list_is_refused():
    s = DRAFT.to(DRAFT.first('pending'), 'posted')
    with pytest.raises(IllegalStateError):
        DRAFT.to(s, 'discarded')  # a posted update is not thrown away
    with pytest.raises(IllegalStateError):
        ASK.of('maybe')
    with pytest.raises(IllegalStateError):
        ASK.of(None)  # a record with no state at all
    with pytest.raises(IllegalStateError):
        POLL.first('paused')
    with pytest.raises(IllegalStateError):
        Machine('broken', {'a': ('b',)})  # a move to a state it never names


def test_a_draft_goes_round_posted_revising_editing_and_back():
    s = DRAFT.first('pending')
    for to in ('posted', 'revising', 'editing', 'posted'):
        s = DRAFT.to(s, to)
    assert s == 'posted' and not DRAFT.can(s, 'editing')


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
