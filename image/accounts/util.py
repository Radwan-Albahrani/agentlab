"""Shared helpers: shell commands, tmux sessions (sign-in flows), HTTP, the browser view, the one-line flash message."""

import contextlib
import os
import signal
import socket
import subprocess
import urllib.error
import urllib.request

AGENT_ID = os.environ.get('AGENT_ID', 'agent')
AGENT_OWNER = os.environ.get('AGENT_OWNER', '')
HOME = os.path.expanduser('~')
FLASH = '/tmp/accounts-flash'
NOVNC_PORT = 6080


PATHS = {
    't3': '',
    'accounts': '/_agentlab/accounts',
    'browser': '/_agentlab/browser',
    'terminal': '/_agentlab/terminal',
}


def published(app):
    """The host port app is published on, or ''."""
    if app == 'hub':
        port = os.environ.get('AGENTLAB_PUBLISHED_HUB', '')
    else:
        pairs = (p.partition('=') for p in os.environ.get('AGENTLAB_PUBLISHED', '').split(',') if p)
        port = {k.strip(): v.strip() for k, _, v in pairs}.get(app, '')
    return port if port.isdigit() else ''


def hostname(host):
    """Bare host name of a Host header ('box:7102' -> 'box'); '' for anything else, IPv6 included."""
    name = (host or '').strip().lower().rsplit(':', 1)[0]
    ok = name and all(c.isalnum() or c in '.-' for c in name) and not name.startswith(('.', '-'))
    return name if ok else ''


def public_url(app, host='', proto='https'):
    """The address people reach app at (via the edge, or a published port); '' if unknown."""
    port, name = published(app), hostname(host)
    if port and name:
        return f'http://{name}:{port}' + (PATHS[app] if app == 'terminal' else '')
    if app == 'hub':
        hub = os.environ.get('AGENTLAB_HUB_DOMAIN', '')
        return f'https://{hub}' if hub else ''
    domain = os.environ.get('AGENTLAB_DOMAIN') or host
    if not domain:
        return ''
    scheme = 'https' if os.environ.get('AGENTLAB_DOMAIN') else proto
    return f'{scheme}://{domain}{PATHS[app]}'


def run(cmd, timeout=20):
    """Run in a login shell -> (exit code, combined output); 124 on timeout."""
    # Own process group so a timeout kills the CLI too, not just bash.
    p = subprocess.Popen(
        ['bash', '-lc', cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True
    )
    try:
        out, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError):
            os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        return 124, ''
    return p.returncode, (out or '').strip()


def sh_quote(s):
    return "'" + s.replace("'", "'\\''") + "'"


def tmux(*args):
    return subprocess.run(['tmux', *args], capture_output=True, text=True, check=False)


def session(flow):
    return f'login-{flow}'


def active(flow):
    return tmux('has-session', '-t', session(flow)).returncode == 0


def screen(flow):
    r = tmux('capture-pane', '-p', '-J', '-t', session(flow))  # -J rejoins wrapped lines (long URLs)
    return r.stdout.rstrip() if r.returncode == 0 else ''


def start_session(flow, cmd):
    """Run cmd in a fresh tmux session that stays open after it finishes, so the page can read the result."""
    tmux('kill-session', '-t', session(flow))
    tmux(
        'new-session',
        '-d',
        '-s',
        session(flow),
        '-x',
        '400',
        '-y',
        '60',
        'bash',
        '-lc',
        f"{cmd}; echo; echo '[login finished]'; sleep 900",
    )


def stop_session(flow):
    tmux('kill-session', '-t', session(flow))


def type_into(flow, text):
    tmux('send-keys', '-t', session(flow), '-l', text)
    tmux('send-keys', '-t', session(flow), 'Enter')


def open_callback(url):
    """Open a sign-in's localhost redirect inside the container (the owner's browser can't reach it)."""
    if not url.startswith('http'):
        url = 'http://' + url
    subprocess.run(['curl', '-s', '-o', '/dev/null', '--max-time', '20', url], capture_output=True, check=False)


def http(url, headers=None, data=None, timeout=15):
    """-> (status, body); status 0 when the server can't be reached."""
    req = urllib.request.Request(url, headers=headers or {}, data=data, method='POST' if data else 'GET')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode(errors='replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors='replace')
    except (OSError, ValueError) as e:
        return 0, str(e)


def browser_up():
    try:
        socket.create_connection(('127.0.0.1', NOVNC_PORT), timeout=1).close()
    except OSError:
        return False
    return True


def flash(msg=None):
    """Set (msg) or take (no argument) the one-shot message shown atop the page."""
    if msg is not None:
        with open(FLASH, 'w') as f:
            f.write(msg)
        return ''
    try:
        with open(FLASH) as f:
            message = f.read()
        os.remove(FLASH)
    except OSError:
        return ''
    return message
