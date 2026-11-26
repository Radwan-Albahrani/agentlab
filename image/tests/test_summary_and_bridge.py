import json
import os
import subprocess

import bridge
import pytest
import summary


@pytest.fixture
def cgroup(tmp_path, monkeypatch):
    monkeypatch.setattr(summary, 'CGROUP', str(tmp_path))
    (tmp_path / 'memory.current').write_text(str(3 * 2**30))
    (tmp_path / 'memory.stat').write_text(f'anon 1\nactive_file {2**30}\ninactive_file {2**29}\n')
    (tmp_path / 'memory.max').write_text(str(12 * 2**30))
    return tmp_path


def test_resources_exclude_file_cache_and_read_the_limit(cgroup, monkeypatch, tmp_path):
    status = tmp_path / 'status.json'
    status.write_text(json.dumps({'running': ['npm run build · web'], 'waiting': ['bun test · api']}))
    monkeypatch.setattr(summary, 'THROTTLE_STATUS', str(status))
    assert summary.resources() == {
        'usedMB': 1536,
        'limitMB': 12288,
        'running': ['npm run build · web'],
        'waiting': ['bun test · api'],
        'paused': 0,
    }


def test_unlimited_and_unreadable(cgroup, monkeypatch):
    (cgroup / 'memory.max').write_text('max\n')
    monkeypatch.setattr(summary, 'THROTTLE_STATUS', '/nonexistent')
    assert summary.resources()['limitMB'] is None and summary.resources()['running'] == []
    monkeypatch.setattr(summary, 'CGROUP', '/nonexistent')
    assert summary.memory() == (None, None)


def test_bridge_runs_the_t3_of_the_running_server(tmp_path):
    assert bridge.t3tools.binary(str(tmp_path)) == 't3'
    (tmp_path / 'userdata').mkdir()
    (tmp_path / 'userdata' / 'server-runtime.json').write_text(json.dumps({'serverVersion': '0.1.9'}))
    assert bridge.t3tools.binary(str(tmp_path)) == 't3'  # that version's binary is gone
    old = tmp_path / 'runtime' / 'versions' / '0.1.9'
    old.mkdir(parents=True)
    (old / 't3').write_text('#!/bin/sh\n')
    (old / 't3').chmod(0o755)
    assert bridge.t3tools.binary(str(tmp_path)) == str(old / 't3')


def test_bridge_key(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, 'KEY_FILE', str(tmp_path / 'bridge-key'))
    assert bridge.authorized('anything') == (False, 'bridge disabled')
    (tmp_path / 'bridge-key').write_text('s3cret\n')
    assert bridge.authorized('s3cret') == (True, '')
    assert bridge.authorized('nope') == (False, 'bad key')
    assert bridge.authorized('') == (False, 'bad key')


def test_bridge_routes_dispatch_to_t3_tools(monkeypatch):
    monkeypatch.setattr(bridge.t3tools, 'answer', lambda thread, message: (True, {'answered': [thread, message]}))
    monkeypatch.setattr(bridge.t3tools, 'interrupt', lambda thread: (False, 'no run'))
    monkeypatch.setattr(bridge.t3tools, 'archive', lambda thread: (True, {'archived': thread}))
    assert bridge.handle('/api/t3/respond', {'thread': 't1', 'message': 'yes'}) == (
        200,
        {'ok': True, 'result': {'answered': ['t1', 'yes']}},
    )
    assert bridge.handle('/api/t3/stop', {'thread': 't1'}) == (500, {'ok': False, 'result': 'no run'})
    assert bridge.handle('/api/t3/archive', {'thread': 't1'}) == (200, {'ok': True, 'result': {'archived': 't1'}})


def test_a_released_chats_worktrees_go_once_its_chats_finish(monkeypatch, tmp_path):
    review, lane, shared = (str(tmp_path / n) for n in ('review', 'lane', 'shared'))
    for w in (review, lane, shared):
        os.makedirs(w)
    answers = iter(
        [
            {review: None, lane: 1.0, shared: None},  # the lead is still writing; a lane is done
            {review: 2.0, lane: 1.0, shared: None},  # all done but one another chat still uses
            {review: 2.0, lane: 1.0, shared: None},  # ... until the watch gives up: the janitor has it
        ]
    )
    removed, slept = [], []

    def run(cmd, input=None, env=None, **kw):
        if cmd[0] == 'agent-t3':
            assert cmd[1:] == ['worktrees-of', 'lead']
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(next(answers)), stderr='')
        assert cmd == ['agent-worktree-remove'] and env['NOTICE_DAYS'] == '0'
        paths = input.split()
        removed.append(paths)
        for w in paths:
            os.rmdir(w)
        return subprocess.CompletedProcess(cmd, 0, stdout=f'removed {len(paths)} worktrees: ...\n', stderr='')

    monkeypatch.setattr(bridge.subprocess, 'run', run)
    clock = iter([0, 60, 120, bridge.RELEASE_FOR_S + 1])
    bridge._release('lead', sleep=slept.append, clock=lambda: next(clock))
    assert removed == [[lane], [review]] and slept == [bridge.RELEASE_EVERY_S] * 2
    assert os.path.exists(shared) and not bridge._releasing


def test_release_gives_up_after_a_while_and_when_t3_cannot_say(monkeypatch):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"/nowhere": null}', stderr='')

    monkeypatch.setattr(bridge.subprocess, 'run', run)
    clock = iter([0, bridge.RELEASE_FOR_S + 1])
    bridge._release('lead', sleep=lambda s: None, clock=lambda: next(clock))
    assert len(calls) == 1
    monkeypatch.setattr(bridge.subprocess, 'run', lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, '', 'no db'))
    bridge._release('lead', sleep=lambda s: pytest.fail('waited'), clock=lambda: 0)
    assert bridge.handle('/api/t3/release', {}) == (500, {'ok': False, 'result': 'no thread'})
