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


def public_url(app, host='', proto='https'):
    """The public address of app (t3, accounts, browser, terminal, hub) as people reach it through the edge: everyone's
    own agent lives on the cluster domain (AGENTLAB_DOMAIN, the edge picks the agent by who signed in), the hub on
    AGENTLAB_HUB_DOMAIN. Without the env, the host the page was opened on stands in for the domain; '' if unknown."""
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
    # Own process group so a timeout kills the CLI too (killing only bash left orphans piling up).
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
    """Run cmd in a fresh tmux session; it stays open after finishing so the page can read the result."""
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
    """A sign-in's redirect to localhost (unreachable from the owner's browser) is opened inside the container."""
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
    """The live browser view (noVNC) runs only while an agent has a browser open."""
    try:
        socket.create_connection(('127.0.0.1', NOVNC_PORT), timeout=1).close()
    except OSError:
        return False
    return True


def flash(msg=None):
    """Set (msg) or take (no argument) the message shown once at the top of the page."""
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
