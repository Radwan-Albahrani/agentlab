"""The base image's launcher (base/run.py): not configured stays down quietly, the checkout's version, and when the
checkout's requirements need a venv."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'base'))
import run


@pytest.fixture
def launcher(tmp_path, monkeypatch):
    for d in ('app', 'data', 'files', 'secrets'):
        (tmp_path / d).mkdir()
    monkeypatch.setattr(run, 'APP', str(tmp_path / 'app'))
    monkeypatch.setattr(run, 'DATA', str(tmp_path / 'data'))
    monkeypatch.setattr(run, 'SECRETS', str(tmp_path / 'secrets'))
    monkeypatch.setattr(run, 'OWN', str(tmp_path / 'files' / 'helper'))
    monkeypatch.setattr(run, 'VENV', str(tmp_path / 'data' / 'venv'))
    monkeypatch.setattr(run.log, 'handlers', [])
    return tmp_path


def test_without_slack_secrets_it_says_not_configured_and_exits_cleanly(launcher):
    (launcher / 'secrets' / 'owner.txt').write_text('U1')
    (launcher / 'secrets' / 'bot-token.txt').write_text('  ')
    assert run.main() == 0
    status = json.loads((launcher / 'files' / 'helper' / 'status.json').read_text())
    assert status['state'] == 'not configured'
    assert 'bot-token.txt' in status['error'] and 'app-token.txt' in status['error']
    assert 'owner.txt' not in status['error']
    assert 'not configured' in (launcher / 'files' / 'helper' / 'logs' / 'companion.log').read_text()


def test_version_is_the_checkouts_commit(launcher):
    git = launcher / 'app' / '.git'
    (git / 'refs' / 'heads').mkdir(parents=True)
    (git / 'HEAD').write_text('ref: refs/heads/main\n')
    assert run.version() == ''  # no such ref yet
    (git / 'packed-refs').write_text('# pack-refs\n0123456789abcdef0123 refs/heads/main\n')
    assert run.version() == '0123456789ab'
    (git / 'refs' / 'heads' / 'main').write_text('fedcba9876543210fedc\n')
    assert run.version() == 'fedcba987654'


def test_unchanged_requirements_run_on_the_image_python(launcher, monkeypatch):
    req = launcher / 'app' / 'requirements.txt'
    req.write_text('slack_bolt==1.29.0\n')
    base = launcher / 'base.sha256'
    base.write_text(run.sha256(str(req)))
    monkeypatch.setattr(run, 'BASE_HASH', str(base))
    assert run.python() == sys.executable


def test_a_failed_install_is_an_error_not_a_hot_loop(launcher, monkeypatch):
    (launcher / 'app' / 'requirements.txt').write_text('surely-not-a-real-package-xyz==0.0.1\n')
    base = launcher / 'base.sha256'
    base.write_text('something else')
    monkeypatch.setattr(run, 'BASE_HASH', str(base))
    for name in run.REQUIRED:
        (launcher / 'secrets' / name).write_text('x')
    monkeypatch.setattr(
        run.subprocess, 'run', lambda cmd, **kw: type('R', (), {'returncode': 1, 'stdout': '', 'stderr': 'nope'})
    )
    assert run.main() == 1
    status = json.loads((launcher / 'files' / 'helper' / 'status.json').read_text())
    assert status['state'] == 'failed' and 'requirements.txt' in status['error']
