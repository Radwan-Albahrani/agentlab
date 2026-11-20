import pytest
from bot import t3
from bot.t3db import Message, Request, Run, Thread, TurnItem

LEAD = 'mcp:lead'
QA = 'thread:provider:claudeAgent:native-thread:provider-thread%3Apending%253Aordinal%253A1%3Aadd228bb765d441b2'
T3_CHILD = 'thread:delegated-task:command%3Amcp%3Adelegate-task%3Ae3a054a1'
PARENT = {'lineage': {'parentThreadId': LEAD}}


def run(n, tid, status, requested, completed):
    return Run(run_id=f'r{n}', thread_id=tid, status=status, requested_at=requested, completed_at=completed)


@pytest.fixture
def chat(t3_rows, monkeypatch):
    now = t3.parse_iso('2026-11-15T22:54:00Z')
    monkeypatch.setattr(t3.time, 'time', lambda: now)
    t3_rows.add_all(
        [
            Thread(thread_id=LEAD, title='Review', updated_at='2026-11-15T22:54:00Z', payload={}),
            Thread(thread_id=QA, title='QA', updated_at='2026-11-15T22:53:50Z', payload=PARENT),
            Thread(thread_id=T3_CHILD, title='Lane', updated_at='2026-11-15T22:50:00Z', payload=PARENT),
            run(1, T3_CHILD, 'completed', '2026-11-15T22:40:00Z', '2026-11-15T22:50:00Z'),
        ]
    )
    t3_rows.commit()
    return t3_rows


def running():
    return {title: r for _, title, r in t3.snapshot(LEAD, '9999')['workers']}


def test_a_claude_subagent_works_until_its_report_reaches_the_lead(chat):
    # it has no T3 runs, so only the lead hearing back (by its agent id) ends it; the review must not end before
    assert running() == {'QA': True, 'Lane': False}
    report = 'This agent\'s report was delivered to you as a message from "add228bb765d441b2".'
    chat.add(
        Message(
            message_id='m1',
            thread_id=LEAD,
            role='user',
            streaming=0,
            created_at='2026-11-15T22:56:16Z',
            payload={'text': report},
        )
    )
    chat.commit()
    assert running() == {'QA': False, 'Lane': False}


def test_a_subagent_silent_for_twenty_minutes_counts_as_gone(chat, monkeypatch):
    later = t3.parse_iso('2026-11-15T23:14:00Z')
    monkeypatch.setattr(t3.time, 'time', lambda: later)
    assert running()['QA'] is False


def test_a_child_run_cut_off_by_a_restart_is_reported_until_resumed(chat):
    chat.add(run(2, T3_CHILD, 'interrupted', '2026-11-15T22:41:00Z', '2026-11-15T22:52:00Z'))
    chat.commit()
    assert t3.snapshot(LEAD, '9999')['interrupted_at'] == '2026-11-15T22:52:00Z'
    chat.add(run(3, T3_CHILD, 'running', '2026-11-15T22:53:00Z', None))  # T3 resumed it
    chat.commit()
    assert t3.snapshot(LEAD, '9999')['interrupted_at'] is None


def test_a_digest_tells_the_quick_model_what_the_chat_is_doing(chat):
    steps = [
        (LEAD, 'reasoning', {'text': 'I am checking the sweep tests'}, 'completed'),
        (LEAD, 'command_execution', {'input': 'bun test sweep'}, 'failed'),
        (LEAD, 'assistant_message', {'text': 'Fixing the failing sweep test now.'}, 'completed'),
        (T3_CHILD, 'assistant_message', {'text': 'Lane done: no findings.'}, 'completed'),
    ]
    chat.add_all(
        TurnItem(turn_item_id=f'i{n}', thread_id=tid, type=typ, ordinal=n, payload=payload, status=status)
        for n, (tid, typ, payload, status) in enumerate(steps, 1)
    )
    chat.commit()
    d = t3.digest(LEAD)
    order = d.index('reasoning: I am checking'), d.index('command execution (failed): bun test sweep')
    assert order[0] < order[1]
    assert 'Worker "Lane": finished; last: assistant message: Lane done: no findings.' in d


def test_open_questions_and_errors_are_read_from_their_rows(chat):
    chat.add_all(
        [
            Request(runtime_request_id='q1', thread_id=LEAD, kind='user_input', status='pending', payload={}),
            TurnItem(turn_item_id='e1', thread_id=LEAD, type='error', ordinal=9, payload={'message': 'capacity'}),
        ]
    )
    chat.commit()
    assert t3.waiting_question(LEAD) and t3.run_error(LEAD) == '{"message": "capacity"}'
    chat.get(Request, 'q1').payload = {'responseCapability': {'type': 'message'}}  # answered by any message
    chat.commit()
    assert not t3.waiting_question(LEAD)
