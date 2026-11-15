import sqlite3

import pytest
from bot import t3

SCHEMA = """
create table orchestration_v2_projection_runs (thread_id text, status text, requested_at text, completed_at text);
create table orchestration_v2_projection_messages (message_id text, thread_id text, role text, streaming int,
  created_at text, payload_json text);
create table orchestration_v2_projection_runtime_requests (runtime_request_id text, thread_id text, kind text,
  status text, payload_json text);
create table orchestration_v2_projection_turn_items (thread_id text, type text, ordinal int, payload_json text);
create table orchestration_v2_projection_threads (thread_id text, title text, updated_at text, payload_json text);
"""
LEAD = 'mcp:lead'
QA = 'thread:provider:claudeAgent:native-thread:provider-thread%3Apending%253Aordinal%253A1%3Aadd228bb765d441b2'
T3_CHILD = 'thread:delegated-task:command%3Amcp%3Adelegate-task%3Ae3a054a1'


@pytest.fixture
def chat(tmp_path, monkeypatch):
    con = sqlite3.connect(tmp_path / 'statev2.sqlite')
    con.executescript(SCHEMA)
    now = t3.parse_iso('2026-11-15T22:54:00Z')
    monkeypatch.setattr(t3, 'db', lambda: sqlite3.connect(tmp_path / 'statev2.sqlite'))
    monkeypatch.setattr(t3.time, 'time', lambda: now)
    parent = f'{{"lineage": {{"parentThreadId": "{LEAD}"}}}}'
    con.execute(
        "insert into orchestration_v2_projection_threads values (?, 'Review', '2026-11-15T22:54:00Z', '{}')", (LEAD,)
    )
    con.execute(
        "insert into orchestration_v2_projection_threads values (?, 'QA', '2026-11-15T22:53:50Z', ?)", (QA, parent)
    )
    con.execute(
        "insert into orchestration_v2_projection_threads values (?, 'Lane', '2026-11-15T22:50:00Z', ?)",
        (T3_CHILD, parent),
    )
    con.execute(
        "insert into orchestration_v2_projection_runs values (?, 'completed', '2026-11-15T22:40:00Z', '2026-11-15T22:50:00Z')",
        (T3_CHILD,),
    )
    con.commit()
    yield con
    con.close()


def running(con):
    return {title: r for _, title, r in t3.snapshot(LEAD, '9999')['workers']}


def test_a_claude_subagent_works_until_its_report_reaches_the_lead(chat):
    # it has no T3 runs, so only the lead hearing back (by its agent id) ends it; the review must not end before
    assert running(chat) == {'QA': True, 'Lane': False}
    chat.execute(
        """insert into orchestration_v2_projection_messages values ('m1', ?, 'user', 0, '2026-11-15T22:56:16Z',
           '{"text": "This agent''s report was delivered to you as a message from \\"add228bb765d441b2\\"."}')""",
        (LEAD,),
    )
    chat.commit()
    assert running(chat) == {'QA': False, 'Lane': False}


def test_a_subagent_silent_for_twenty_minutes_counts_as_gone(chat, monkeypatch):
    later = t3.parse_iso('2026-11-15T23:14:00Z')
    monkeypatch.setattr(t3.time, 'time', lambda: later)
    assert running(chat)['QA'] is False
