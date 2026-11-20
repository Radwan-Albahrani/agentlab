import json
import time

import pytest
import t3state
from conftest import load_script, t3_db
from sqlalchemy import Engine, event
from t3schema import Run, Thread

agent_t3 = load_script('agent-t3')


def stamp(t):
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(t))


def thread(tid, wt, **payload):
    deleted = payload.pop('deleted', None)
    return Thread(thread_id=tid, deleted_at=deleted, payload={'worktreePath': wt and f'/w/{wt}', **payload})


@pytest.fixture
def queries():
    """Every SQL statement the code under test sends."""
    seen = []

    def count(conn, cursor, statement, *_):
        seen.append(statement)

    event.listen(Engine, 'before_cursor_execute', count)
    yield seen
    event.remove(Engine, 'before_cursor_execute', count)


def test_busy_means_a_run_with_no_end_time_and_no_finished_status(tmp_path):
    db = t3_db(
        tmp_path / 's.db',
        Run(run_id='r1', thread_id='t', status='completed'),
        Run(run_id='r2', thread_id='t', status='some_new_status', completed_at='2026-11-04T11:48:15.816Z'),
    )
    with t3state.reading(db) as s:
        assert not t3state.busy(s)
    db = t3_db(tmp_path / 'b.db', Run(run_id='r1', thread_id='t', status='running'))
    with t3state.reading(db) as s:
        assert t3state.busy(s)


def test_inflight_is_every_run_without_a_finished_status(tmp_path):
    db = t3_db(
        tmp_path / 's.db',
        Run(run_id='r1', thread_id='t1', status='running'),
        Run(run_id='r2', thread_id='t2', status='completed'),
        Run(run_id='r3', thread_id='t1', status='odd', completed_at='2026-11-04T11:48:15.816Z'),
        Run(run_id='r4', thread_id='t3', status=None),  # SQL: null is not "not in"
    )
    with t3state.reading(db) as s:
        assert sorted(t3state.inflight(s)) == [('r1', 't1'), ('r3', 't1')]


def test_worktrees_say_when_their_chats_finished_in_two_queries(tmp_path, queries):
    now = int(time.time())
    old, fresh = now - 20 * 3600, now - 3600
    db = t3_db(
        tmp_path / 's.db',
        thread('t1', 'done', settledAt=stamp(old)),
        thread('t2', 'recent', settledAt=stamp(fresh)),
        thread('t3', 'live', settledAt=None),
        thread('t4', 'delegated', settledAt=None),
        thread('t5', 'delegated-now', settledAt=None),
        thread('t6', 'shared', settledAt=stamp(old)),
        thread('t7', 'shared', settledAt=None),
        thread('t8', 'shared', settledAt=stamp(fresh)),
        thread('t9', 'gone', settledAt=None, deleted=stamp(old)),
        thread('t10', 'reopened', settledAt=stamp(old), unsettledAt=stamp(fresh)),
        thread('t11', None),
        Run(run_id='r1', thread_id='t3', status='running'),
        Run(run_id='r2', thread_id='t4', completed_at=stamp(old)),
        Run(run_id='r3', thread_id='t4', completed_at=stamp(old)),
        Run(run_id='r4', thread_id='t5', completed_at=stamp(old)),
        Run(run_id='r5', thread_id='t5', completed_at=stamp(fresh)),
        Run(run_id='r6', thread_id='t7', status='running'),
    )
    queries.clear()
    with t3state.reading(db) as s:
        got = t3state.worktrees(s)
    assert got == {
        '/w/done': old,
        '/w/recent': fresh,
        '/w/live': None,
        '/w/delegated': old,
        '/w/delegated-now': fresh,
        '/w/shared': None,  # one live chat keeps it, whichever comes first
        '/w/gone': old,
        '/w/reopened': None,
    }
    assert len(queries) == 2


def test_the_command_answers_in_json_and_no_database_means_no_chats(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(t3state, 'DB', str(tmp_path / 'missing.sqlite'))
    for question, want in (('busy', False), ('inflight', []), ('worktrees', None)):
        assert agent_t3.main([question]) == 0
        assert json.loads(capsys.readouterr().out) == want
    monkeypatch.setattr(t3state, 'DB', t3_db(tmp_path / 's.db', Run(run_id='r1', thread_id='t1', status='running')))
    assert agent_t3.main(['inflight']) == 0
    assert json.loads(capsys.readouterr().out) == [['r1', 't1']]
    assert agent_t3.main(['busy']) == 0
    assert json.loads(capsys.readouterr().out) is True


def test_an_unreadable_database_or_question_exits_non_zero(tmp_path, monkeypatch, capsys):
    bad = tmp_path / 'bad.sqlite'
    bad.write_text('not a database')
    monkeypatch.setattr(t3state, 'DB', str(bad))
    assert t3state.main(['busy']) == 1
    assert t3state.main(['what']) == 2
    assert capsys.readouterr().out == ''
