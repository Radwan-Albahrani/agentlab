import io
import json
import os
import stat
import threading
import time
import urllib.parse

import pytest
from conftest import load_script

companion = load_script('companion')


@pytest.fixture
def home(tmp_path, monkeypatch):
    for attr, sub in (('REQUESTS', 'requests'), ('RESULTS', 'results'), ('STATE', 'state'), ('CODE', 'code')):
        monkeypatch.setattr(companion, attr, str(tmp_path / sub))
    monkeypatch.setattr(companion, 'LIVE', str(tmp_path / 'companions.json'))
    # generous: a busy CI box can starve the fake watcher thread for a few seconds; answered requests return at once
    monkeypatch.setattr(companion, 'WAIT_S', 15)
    monkeypatch.setattr(companion, 'CREATE_WAIT_S', 15)
    monkeypatch.setenv('AGENTLAB_COMPANIONS', 'helper, bad/name,other')
    (tmp_path / 'results').mkdir()
    return tmp_path


def watcher(home, base, answer, seen):
    """A stand-in for the host's watcher: takes the request (keeping what it said) and answers it."""

    def run():
        request = home / 'requests' / base
        while not request.exists():
            time.sleep(0.02)
        seen['mode'] = stat.S_IMODE(os.stat(request).st_mode)
        seen['payload'] = json.loads(request.read_text())
        request.unlink()
        tmp = home / 'results' / f'.{base}.tmp'
        tmp.write_text(json.dumps(answer))
        tmp.replace(home / 'results' / f'{base}.json')  # like the real watcher: never a half-written answer

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def test_names_come_from_the_live_list_else_the_env(home):
    assert companion.names() == ['helper', 'other']
    (home / 'companions.json').write_text(json.dumps([{'name': 'scout'}, 'helper']))
    assert companion.names() == ['scout', 'helper']
    with pytest.raises(SystemExit):
        companion.known('../etc')


def test_restart_writes_the_request_and_prints_the_answer(home, capsys):
    seen = {}
    watcher(home, 'restart~companion~helper', {'ok': True, 'state': 'running'}, seen)
    companion.cmd_action('restart', 'helper')
    assert '"state": "running"' in capsys.readouterr().out and 'at' in seen['payload']


def test_a_failed_action_exits_nonzero_and_silence_times_out(home):
    (home / 'results' / 'stop~companion~helper.json').write_text('{"ok": false}')
    with pytest.raises(SystemExit):  # the stale result is removed first, so this one times out
        companion.cmd_action('stop', 'helper')
    assert (home / 'requests' / 'stop~companion~helper').exists()


def test_secret_comes_from_stdin_in_a_private_file_and_is_dropped_if_unanswered(home, monkeypatch):
    seen = {}
    monkeypatch.setattr('sys.stdin', io.StringIO('xoxb-example\n'))
    watcher(home, 'secret~companion~helper', {'ok': True, 'key': 'bot-token.txt'}, seen)
    companion.cmd_secret('helper', 'bot-token.txt')
    assert seen == {'mode': 0o600, 'payload': {'key': 'bot-token.txt', 'value': 'xoxb-example'}}
    monkeypatch.setattr('sys.stdin', io.StringIO('xapp-1'))
    with pytest.raises(SystemExit):
        companion.cmd_secret('helper', 'app-token.txt')
    assert not (home / 'requests' / 'secret~companion~helper').exists()
    with pytest.raises(SystemExit):
        companion.cmd_secret('helper', '../../etc/passwd')


def test_settings_are_sent_as_the_object_itself(home, tmp_path):
    seen = {}
    watcher(home, 'settings~companion~helper', {'ok': True}, seen)
    (tmp_path / 's.json').write_text('{"mode": "team"}')
    companion.cmd_settings('helper', f'@{tmp_path / "s.json"}')
    assert seen['payload'] == {'mode': 'team'}
    with pytest.raises(SystemExit):
        companion.cmd_settings('helper', '[1, 2]')


def test_create_prints_checkout_and_a_renamed_slack_manifest_link(home, capsys):
    code = home / 'code' / 'scout'
    code.mkdir(parents=True)
    (code / 'slack-manifest.yml').write_text(
        '# comment\ndisplay_information:\n  name: Companion\nfeatures:\n  bot_user:\n    display_name: Companion\n'
        'oauth_config:\n  scopes:\n    bot:\n      - chat:write\n'
    )
    seen = {}
    watcher(home, 'create~companion~scout', {'ok': True}, seen)
    companion.cmd_create('scout', 'Scout Bot', 'slack')
    assert seen['payload'] == {'display_name': 'Scout Bot', 'kind': 'slack'}
    out = capsys.readouterr().out
    link = next(line for line in out.splitlines() if line.startswith(companion.SLACK_NEW_APP))
    manifest = urllib.parse.unquote(link[len(companion.SLACK_NEW_APP) :])
    assert '  name: "Scout Bot"' in manifest and '    display_name: "Scout Bot"' in manifest
    assert '# comment' not in manifest and '- chat:write' in manifest


def test_create_refuses_bad_or_taken_names(home):
    for name, kind in (('Bad Name', 'slack'), ('helper', 'slack'), ('fresh', 'irc')):
        with pytest.raises(SystemExit):
            companion.cmd_create(name, '', kind)


def test_status_line(home):
    (home / 'state' / 'helper').mkdir(parents=True)
    (home / 'state' / 'helper' / 'status.json').write_text(json.dumps({'heartbeat': time.time() - 30, 'error': 'boom'}))
    line = companion.one_line('helper')
    assert line.startswith('helper: running · heartbeat 30 s ago') and 'last error: boom' in line
    assert 'no status yet' in companion.one_line('other')
