import os
import sqlite3
import subprocess
import time

import pytest
from conftest import load_script

updater = load_script('agent-updater')

PS_015 = 'bash -lc exec t3 serve\n/home/agent/.t3/runtime/versions/0.1.5/t3 serve --host 0.0.0.0 --port 3773\n'


def runs_db(path, *statuses):
    with sqlite3.connect(path) as c:
        c.execute('create table orchestration_v2_projection_runs (run_id text, status text)')
        c.executemany(
            'insert into orchestration_v2_projection_runs values (?, ?)', [(str(i), s) for i, s in enumerate(statuses)]
        )
    return str(path)


class Runner:
    """Stands in for subprocess.run: answers `t3 --version`, records everything else."""

    def __init__(self, t3='t3 v0.1.6'):
        self.t3, self.calls = t3, []

    def __call__(self, cmd, **_):
        self.calls.append(cmd)
        out = self.t3 if cmd[-1] == 't3 --version' else ''
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr='')

    @property
    def restarted(self):
        return [c for c in self.calls if c[-2:] == ['restart', 't3']]


def test_reads_the_running_version_from_the_server_binary_path():
    assert updater.running_t3(PS_015) == '0.1.5'
    assert updater.running_t3('python3 app.py\n') == ''


def test_restarts_t3_when_a_newer_one_is_installed_and_nothing_runs(tmp_path):
    run = Runner()
    db = runs_db(tmp_path / 's.db', 'completed', 'cancelled', 'failed', 'interrupted')
    assert updater.align_t3(run, PS_015, db) == 'restarted'
    assert run.restarted == [[*updater.SUPERVISOR, 'restart', 't3']]


def test_never_restarts_mid_turn(tmp_path):
    run = Runner()
    db = runs_db(tmp_path / 's.db', 'completed', 'running')
    assert updater.align_t3(run, PS_015, db) == 'busy'
    assert run.restarted == []


def test_an_unreadable_db_counts_as_busy(tmp_path):
    run = Runner()
    assert updater.align_t3(run, PS_015, str(tmp_path / 'missing.db')) == 'busy'
    assert run.restarted == []


def test_same_version_or_unknown_leaves_t3_alone(tmp_path):
    db = runs_db(tmp_path / 's.db')
    run = Runner(t3='t3 v0.1.5')
    assert updater.align_t3(run, PS_015, db) == 'current'
    run = Runner()
    assert updater.align_t3(run, 'no t3 here\n', db) == 'unknown'
    assert run.restarted == []


def test_installs_only_when_due_and_never_when_off(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, 'STAMP', str(tmp_path / 'stamp'))
    monkeypatch.setattr(updater, 'HOURS', 6)
    assert updater.due()
    run = Runner()
    updater.update_tools(run)
    assert 'update_tools' in run.calls[0][-1] and run.calls[0][:2] == ['nice', '-n']
    assert not updater.due()
    assert updater.due(time.time() + 6 * 3600 + 1)
    monkeypatch.setattr(updater, 'HOURS', 0)
    os.remove(updater.STAMP)
    assert not updater.due()


@pytest.mark.parametrize(('text', 'want'), [('t3 v0.1.6', '0.1.6'), ('0.2.0-beta.1\n', '0.2.0-beta.1'), ('', '')])
def test_version_parsing(text, want):
    assert updater.version(text) == want


def runs_with_threads(path, rows):
    with sqlite3.connect(path) as c:
        c.execute('create table orchestration_v2_projection_runs (run_id text, thread_id text, status text)')
        c.executemany('insert into orchestration_v2_projection_runs values (?, ?, ?)', rows)
    return str(path)


class Restarting(Runner):
    """A restart marks running runs interrupted, as T3 does on start."""

    def __init__(self, db, t3='t3 v0.1.6'):
        super().__init__(t3)
        self.db = db

    def __call__(self, cmd, **kw):
        if cmd[-2:] == ['restart', 't3']:
            with sqlite3.connect(self.db) as c:
                c.execute("update orchestration_v2_projection_runs set status = 'interrupted' where status = 'running'")
        if cmd[:3] == ['t3', 'thread', 'send']:
            self.calls.append((cmd, kw.get('input')))
            return subprocess.CompletedProcess(cmd, 0, stdout='{}', stderr='')
        return super().__call__(cmd, **kw)

    @property
    def sent(self):
        return [(c[0][4], c[1]) for c in self.calls if isinstance(c, tuple)]


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def test_waits_while_busy_then_restarts_once_idle(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, 'WAIT_HOURS', 4)
    db = runs_with_threads(tmp_path / 's.db', [('r1', 't1', 'running')])
    clock, run = Clock(), Runner()
    waiter = updater.Waiter(clock)
    assert waiter.step(run, PS_015, db) == 'busy'
    clock.t += 3600
    assert waiter.step(run, PS_015, db) == 'busy'
    with sqlite3.connect(db) as c:
        c.execute("update orchestration_v2_projection_runs set status = 'completed'")
    assert waiter.step(run, PS_015, db) == 'restarted'
    assert len(run.restarted) == 1


def test_defers_at_the_end_of_the_window(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, 'WAIT_HOURS', 4)
    monkeypatch.setattr(updater, 'ON_BUSY', 'defer')
    db = runs_with_threads(tmp_path / 's.db', [('r1', 't1', 'running')])
    clock, run = Clock(), Runner()
    waiter = updater.Waiter(clock)
    assert waiter.step(run, PS_015, db) == 'busy'
    clock.t += 4 * 3600
    assert waiter.step(run, PS_015, db) == 'deferred'
    clock.t += 60
    assert waiter.step(run, PS_015, db) == 'deferred'
    assert run.restarted == []


def test_resume_restarts_and_leaves_the_cut_off_turns_to_t3(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, 'WAIT_HOURS', 4)
    monkeypatch.setattr(updater, 'ON_BUSY', 'resume')
    rows = [('r1', 't1', 'running'), ('r2', 't2', 'running'), ('r3', 't3', 'completed'), ('r4', 't1', 'running')]
    db = runs_with_threads(tmp_path / 's.db', rows)
    clock, run = Clock(), Restarting(db)
    waiter = updater.Waiter(clock)
    assert waiter.step(run, PS_015, db) == 'busy'
    clock.t += 4 * 3600
    assert waiter.step(run, PS_015, db, sleep=lambda _: None) == 'resumed'
    assert len(run.restarted) == 1
    assert run.sent == []
