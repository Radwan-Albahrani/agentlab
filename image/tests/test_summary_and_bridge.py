import json

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
    assert bridge.handle('/api/t3/respond', {'thread': 't1', 'message': 'yes'}) == (
        200,
        {'ok': True, 'result': {'answered': ['t1', 'yes']}},
    )
    assert bridge.handle('/api/t3/stop', {'thread': 't1'}) == (500, {'ok': False, 'result': 'no run'})
