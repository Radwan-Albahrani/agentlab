"""Companion bridge into this agent's T3, keyed by ~/.config/agent/bridge-key (no file = bridge off)."""

import json
import os
import subprocess
import threading

import t3tools
from util import HOME

KEY_FILE = os.path.join(HOME, '.config', 'agent', 'bridge-key')
ROUTES = (
    '/api/t3/start',
    '/api/t3/send',
    '/api/t3/respond',
    '/api/t3/stop',
    '/api/t3/archive',
    '/api/t3/release',
    '/api/t3/triage',
)
T3_SETTINGS = os.path.join(HOME, '.t3', 'userdata', 'settings.json')
_releasing: set[str] = set()
_lock = threading.Lock()


def authorized(key):
    try:
        with open(KEY_FILE) as f:
            want = f.read().strip()
    except OSError:
        return False, 'bridge disabled'
    return (True, '') if want and key == want else (False, 'bad key')


def handle(path, body):
    if path == '/api/t3/triage':
        return _result(*triage(str(body.get('message', ''))[:20000]))
    if path == '/api/t3/respond':
        return _result(*t3tools.answer(str(body.get('thread', '')), str(body.get('message', ''))))
    if path == '/api/t3/stop':
        return _result(*t3tools.interrupt(str(body.get('thread', ''))))
    if path == '/api/t3/archive':
        return _result(*t3tools.archive(str(body.get('thread', ''))))
    if path == '/api/t3/release':
        return _result(*release(str(body.get('thread', ''))))
    if path == '/api/t3/start':
        title = ['--title', str(body['title'])[:120]] if body.get('title') else []
        return _thread_cli(['start', '--json', *title, str(body.get('project') or '/workspace'), '-'], body)
    return _thread_cli(['send', '--json', str(body.get('thread', '')), '-'], body)


def _result(ok, out):
    return (200 if ok else 500), {'ok': ok, 'result': out}


def _thread_cli(args, body):
    try:
        p = subprocess.run(
            [t3tools.binary(), 'thread', *args],
            input=str(body.get('message', '')),
            capture_output=True,
            text=True,
            timeout=90,
            cwd='/workspace',
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 504, {'error': 't3 timed out'}
    try:
        out = json.loads(p.stdout)
    except ValueError:
        out = {'raw': p.stdout[-2000:]}
    return (200 if p.returncode == 0 else 500), {'ok': p.returncode == 0, 'result': out, 'stderr': p.stderr[-1000:]}


def release(thread):
    """A finished PR review: the worktrees of its chat and its workers are dropped now, in the background (they only
    read the code, so nothing in them is kept) -> (ok, detail)."""
    if not thread:
        return False, 'no thread'
    with _lock:
        if thread not in _releasing:
            _releasing.add(thread)
            threading.Thread(target=_release, args=(thread,), daemon=True).start()
    return True, {'releasing': thread}


def _release(thread):
    try:
        trees = [w for w in _worktrees_of(thread) or {} if os.path.exists(w)]
        if trees:
            print(f'release {thread}: {_remove(trees)}', flush=True)
    finally:
        with _lock:
            _releasing.discard(thread)


def _worktrees_of(thread):
    """{worktree: finished at | None while a chat on it runs} for the chat and its workers; None if T3 can't say."""
    try:
        p = subprocess.run(
            ['agent-t3', 'worktrees-of', thread], capture_output=True, text=True, timeout=120, check=False
        )
        got = json.loads(p.stdout) if p.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return got if isinstance(got, dict) else None


def _remove(paths):
    """agent-worktree-remove, keeping nothing -> its summary line."""
    try:
        p = subprocess.run(
            ['agent-worktree-remove'],
            input=''.join(f'{w}\n' for w in paths),
            env={**os.environ, 'DISCARD': '1', 'DRY': ''},
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return f'{type(e).__name__}: {e}'
    return (p.stdout.strip().splitlines() or [p.stderr.strip()[-300:]])[-1]


def default_model():
    try:
        with open(T3_SETTINGS) as f:
            return json.load(f).get('defaultModelSelection', {}).get('model', '')
    except (OSError, ValueError):
        return ''


def triage(prompt):
    """One quick read-only model call on the T3 default provider -> (ok, text)."""
    out = f'/tmp/triage-{os.getpid()}-{threading.get_ident()}.txt'
    try:
        if default_model().startswith('claude'):
            p = subprocess.run(
                ['claude', '-p', '--model', 'haiku', '--max-turns', '1'],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=120,
                cwd='/tmp',
                check=False,
            )
            return p.returncode == 0 and bool(p.stdout.strip()), p.stdout.strip() or p.stderr[-300:]
        p = subprocess.run(
            [
                'codex',
                'exec',
                '--skip-git-repo-check',
                '--ephemeral',
                '-s',
                'read-only',
                '-c',
                'model_reasoning_effort="low"',
                '-o',
                out,
                '-',
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
            cwd='/tmp',
            check=False,
        )
        text = ''
        if os.path.exists(out):
            with open(out) as f:
                text = f.read()
        return p.returncode == 0 and bool(text), text or p.stderr[-300:]
    except (OSError, subprocess.SubprocessError) as e:
        return False, f'{type(e).__name__}: {e}'[:300]
    finally:
        if os.path.exists(out):
            os.remove(out)
