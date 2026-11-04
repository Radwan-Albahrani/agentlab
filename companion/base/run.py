#!/usr/bin/env python3
"""Base image launcher for `python -m bot` in /app; baked into the image (not read from /app), so edits need a rebuild."""

import hashlib
import json
import logging
import logging.handlers
import os
import subprocess
import sys
import threading
import time

APP = '/app'
DATA = os.environ.get('COMPANION_DATA', '/data')
SECRETS = os.environ.get('COMPANION_SECRETS', '/secrets')
ID = os.environ.get('COMPANION_ID', os.environ.get('COMPANION_NAME', 'Companion').lower())
OWN = os.path.join(os.environ.get('COMPANION_FILES', '/files'), ID)
BASE_HASH = '/etc/companion/requirements.sha256'  # written at image build
VENV = os.path.join(DATA, 'venv')
REQUIRED = ('owner.txt', 'bot-token.txt', 'app-token.txt', 'agent-key.txt')
ERROR_WORDS = ('failed', 'error', 'traceback', 'exception')

status = {'name': ID, 'state': 'starting', 'since': time.time(), 'heartbeat': None, 'version': '', 'error': ''}
log = logging.getLogger('companion')


def setup_logs():
    os.makedirs(os.path.join(OWN, 'logs'), exist_ok=True)
    log.setLevel(logging.INFO)
    for h in (
        logging.StreamHandler(sys.stdout),
        logging.handlers.RotatingFileHandler(
            os.path.join(OWN, 'logs', 'companion.log'), maxBytes=5 * 1024 * 1024, backupCount=3
        ),
    ):
        h.setFormatter(logging.Formatter('%(message)s'))
        log.addHandler(h)


def say(msg):
    log.info('%s %s', time.strftime('%H:%M:%S'), msg)


def write_status(**changes):
    status.update(changes, updated=time.time())
    try:
        with open(os.path.join(DATA, 'heartbeat.json')) as f:
            status['heartbeat'] = json.load(f).get('at')
    except (OSError, ValueError):
        pass
    tmp = os.path.join(OWN, 'status.json.tmp')
    with open(tmp, 'w') as f:
        json.dump(status, f, indent=1)
    os.replace(tmp, os.path.join(OWN, 'status.json'))


def version():
    """The checkout's short commit, read from .git without git; '' if unreadable."""
    git = os.path.join(APP, '.git')
    try:
        with open(os.path.join(git, 'HEAD')) as f:
            head = f.read().strip()
        if not head.startswith('ref: '):
            return head[:12]
        ref = head[5:]
        try:
            with open(os.path.join(git, ref)) as f:
                return f.read().strip()[:12]
        except OSError:
            with open(os.path.join(git, 'packed-refs')) as f:
                return next((line.split()[0][:12] for line in f if line.rstrip().endswith(' ' + ref)), '')
    except OSError:
        return ''


def missing_secrets():
    out = []
    for name in REQUIRED:
        try:
            with open(os.path.join(SECRETS, name)) as f:
                if not f.read().strip():
                    out.append(name)
        except OSError:
            out.append(name)
    return out


def sha256(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def python():
    """The image's interpreter, or the venv's when the checkout needs other packages."""
    req = os.path.join(APP, 'requirements.txt')
    if not os.path.isfile(req):
        return sys.executable
    want = sha256(req)
    with open(BASE_HASH) as f:
        if f.read().strip() == want:
            return sys.executable
    stamp = os.path.join(VENV, '.requirements.sha256')
    venv_py = os.path.join(VENV, 'bin', 'python')
    try:
        with open(stamp) as f:
            if f.read().strip() == want and os.path.exists(venv_py):
                return venv_py
    except OSError:
        pass
    say('requirements.txt changed: installing into /data/venv')
    write_status(state='installing')
    steps = (
        [sys.executable, '-m', 'venv', '--clear', '--system-site-packages', VENV],
        [venv_py, '-m', 'pip', 'install', '--no-cache-dir', '--disable-pip-version-check', '-q', '-r', req],
    )
    for cmd in steps:
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if r.returncode:
            for line in (r.stdout + r.stderr).strip().splitlines()[-30:]:
                say(line)
            raise RuntimeError(f'installing requirements.txt failed ({cmd[2] if cmd[1] == "-m" else cmd[0]})')
    with open(stamp, 'w') as f:
        f.write(want)
    return venv_py


def keep_status(stop):
    while not stop.wait(10):
        write_status()


def main():
    setup_logs()
    write_status(state='starting', version=version())
    missing = missing_secrets()
    if missing:
        msg = f'not configured: missing {", ".join(missing)} (add them on the hub, then restart)'
        say(msg)
        write_status(state='not configured', error=msg)
        return 0
    try:
        py = python()
    except RuntimeError as e:
        say(str(e))
        write_status(state='failed', error=str(e))
        return 1
    say(f'starting {ID} at {status["version"] or "an unversioned checkout"}')
    write_status(state='running', error='')
    env = dict(os.environ, PYTHONPATH=APP, PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1')
    proc = subprocess.Popen(
        [py, '-u', '-m', 'bot'], cwd=APP, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    stop = threading.Event()
    threading.Thread(target=keep_status, args=(stop,), daemon=True).start()
    tail = []
    for raw in proc.stdout:
        line = raw.rstrip('\n')
        log.info('%s', line)
        tail = [*tail[-19:], line]
        if any(w in line.lower() for w in ERROR_WORDS):
            status['error'] = line[-500:]
    code = proc.wait()
    stop.set()
    if code:
        write_status(state='failed', error=status['error'] or '\n'.join(tail[-5:])[-500:])
        say(f'stopped with exit code {code}')
    else:
        write_status(state='stopped')
    return code


if __name__ == '__main__':
    sys.exit(main())
