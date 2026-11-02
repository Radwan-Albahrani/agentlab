"""Claude / Codex / GitHub sign-in through each official CLI, driven in tmux (device code, link + pasted code)."""

import json
import os
import re
import threading
import time

import connectors
from util import active, flash, open_callback, run, screen, session, start_session, stop_session, tmux, type_into

FLOWS = {
    'claude': {
        'name': 'Claude',
        'login': 'claude auth login',
        'logout': 'claude auth logout',
        'hint': 'Approve with the Claude account this agent should use. If the page shows a code, paste it below.',
    },
    'codex': {
        'name': 'Codex',
        'login': 'codex login --device-auth',
        'logout': 'codex logout',
        'hint': 'Open the link, sign in with ChatGPT and enter the code shown here.',
    },
    # GH_PROMPT_DISABLED skips gh's questions; git credentials are wired up after sign-in.
    'github': {
        'name': 'GitHub',
        'login': 'GH_PROMPT_DISABLED=1 gh auth login --hostname github.com --git-protocol https '
        '--web --scopes workflow --skip-ssh-key --insecure-storage',
        'logout': 'gh auth logout --hostname github.com </dev/null',
        'hint': 'Open the link and enter the code. This signs in git, the gh CLI and the GitHub MCP server.',
    },
}
AI_FLOWS = ('claude', 'codex')
CODEX_BROWSER_LOGIN = 'codex login'  # for workspaces with device-code login turned off
CODEX_CALLBACK_RE = re.compile(r'^(https?://)?(localhost|127\.0\.0\.1):1455/\S+$')  # Safari drops "http://"
URL_RE = re.compile(r'https://\S+')
DEVICE_CODE_RE = re.compile(r'\b[A-Z0-9]{4}-[A-Z0-9]{4,5}\b')
KEYS = {'Enter': 'Enter', '↑': 'Up', '↓': 'Down', 'Esc': 'Escape'}
GH_WIRED = '/tmp/gh-post-done'

# The last known status, refreshed in the background: under load `codex login status` can take minutes.
STATUS_TTL = 60
_status = {}  # flow -> (at, signed_in, detail)
_busy = set()
_lock = threading.Lock()


def mode(flow):
    try:
        return open(f'/tmp/{session(flow)}.mode').read().strip()
    except OSError:
        return 'default'


def status(flow, fresh=False):
    """-> (signed_in, detail). fresh=True waits for a new check (right after a sign-in)."""
    at, ok, detail = _status.get(flow, (0, False, ''))
    if fresh or not at:
        refresh(flow)
        _, ok, detail = _status.get(flow, (0, False, ''))
    elif time.time() - at > STATUS_TTL or active(flow):
        threading.Thread(target=refresh, args=(flow,), daemon=True).start()
    return ok, detail


def refresh(flow):
    with _lock:
        if flow in _busy:
            return
        _busy.add(flow)
    try:
        _status[flow] = (time.time(), *_check(flow))
    finally:
        _busy.discard(flow)


def _check(flow):
    if flow == 'claude':
        rc, out = run('claude auth status')
        try:
            d = json.loads(out)
        except ValueError:
            return rc == 0, ''
        if d.get('authMethod') in (None, 'none') or rc != 0:
            return False, ''
        acct = d.get('account') if isinstance(d.get('account'), dict) else {}
        who = d.get('email') or acct.get('email') or d.get('organizationName') or ''
        plan = d.get('subscriptionType') or acct.get('subscriptionType') or d.get('authMethod', '')
        return True, ' · '.join(x for x in (who, plan) if x)
    if flow == 'github':
        rc, out = run('gh api user --jq .login')
        return (True, f'@{out}') if rc == 0 and out else (False, '')
    rc, out = run('codex login status')
    ok = rc == 0 and not re.search(r'not logged in', out, re.I)
    return ok, out.splitlines()[0] if ok and out else ''


def after_github_login():
    """git uses gh's credentials, and the GitHub MCP server uses gh's token."""
    run('gh auth setup-git')
    rc, tok = run('gh auth token')
    if rc != 0 or not tok:
        return
    header = f'Bearer {tok}'
    if connectors.token_works(connectors.GITHUB_MCP, header):
        connectors.register_token('github', connectors.GITHUB_MCP, header, status('github', fresh=True)[1])
    else:
        flash(
            'GitHub sign-in worked for git and gh, but the GitHub MCP server refused that token. '
            'Paste a personal access token on the GitHub row to enable the MCP tools.'
        )


def state(flow):
    """Everything the page shows for one sign-in, including a live flow's link, code and terminal."""
    signed_in, detail = status(flow)
    scr = screen(flow) if active(flow) else ''
    urls = [u.rstrip('.,)') for u in URL_RE.findall(scr)]
    code = DEVICE_CODE_RE.search(scr) if flow in ('codex', 'github') and mode(flow) != 'browser' else None
    done = signed_in and (
        bool(re.search(r'success|logged in|signed in|authentication complete', scr, re.I)) or flow == 'github'
    )
    if flow == 'github' and signed_in and not os.path.exists(GH_WIRED):  # once per container run, however it signed in
        open(GH_WIRED, 'w').close()
        if 'github' not in connectors.load() or not run('git config --global --get-regexp credential')[1]:
            after_github_login()
    url, code = (urls[0] if urls else ''), (code.group(0) if code else '')
    return {
        'signedIn': signed_in,
        'detail': detail,
        'active': active(flow),
        'url': url,
        'code': code,
        'done': done,
        'screen': scr[-4000:],
    }


def start(flow, how='default'):
    if flow == 'github' and os.path.exists(GH_WIRED):
        os.remove(GH_WIRED)
    with open(f'/tmp/{session(flow)}.mode', 'w') as f:
        f.write(how)
    start_session(flow, CODEX_BROWSER_LOGIN if flow == 'codex' and how == 'browser' else FLOWS[flow]['login'])


def send(flow, text):
    """A pasted code, or (Codex browser login) the localhost:1455 address the browser could not open."""
    if flow == 'codex' and CODEX_CALLBACK_RE.match(text):
        open_callback(text)
    else:
        type_into(flow, text)


def key(flow, name):
    if name in KEYS.values():
        tmux('send-keys', '-t', session(flow), name)


def stop(flow):
    stop_session(flow)


def logout(flow):
    run(FLOWS[flow]['logout'])
    _status.pop(flow, None)
    if flow == 'github':
        connectors.unregister('github')


def save_github_token(token):
    header = f'Bearer {token}'
    if not connectors.token_works(connectors.GITHUB_MCP, header):
        return 'The GitHub MCP server rejected that token. Check it has the repo and read:org scopes.'
    connectors.register_token('github', connectors.GITHUB_MCP, header, status('github')[1])
    return ''
