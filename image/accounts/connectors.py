"""MCP connectors, registered for both Claude Code and Codex. OAuth servers share ONE sign-in: both CLIs run
them through mcp-remote, whose token in ~/.mcp-auth (keyed by the URL's md5) they share. GitHub's server uses gh's
token instead (see signin.after_github_login)."""

import glob
import hashlib
import json
import os
import pathlib
import re
from urllib.parse import urlparse

from util import HOME, active, http, run, screen, sh_quote, start_session, stop_session

STORE = os.path.join(HOME, '.config', 'agent', 'mcp.json')  # {name: {url, shared} | {url, header, who}}
MCP_REMOTE = os.path.join(HOME, '.npm-global', 'bin', 'mcp-remote')
MCP_REMOTE_CLIENT = os.path.join(HOME, '.npm-global', 'bin', 'mcp-remote-client')
MCP_AUTH = os.path.join(HOME, '.mcp-auth')
GITHUB_MCP = 'https://api.githubcopilot.com/mcp/'
CATALOG = {
    'linear': {'name': 'Linear', 'url': 'https://mcp.linear.app/mcp', 'what': 'Issues, projects, comments'},
    'sentry': {'name': 'Sentry', 'url': 'https://mcp.sentry.dev/mcp', 'what': 'Errors, issues, releases'},
    'notion': {'name': 'Notion', 'url': 'https://mcp.notion.com/mcp', 'what': 'Pages and databases'},
    'atlassian': {'name': 'Atlassian', 'url': 'https://mcp.atlassian.com/v1/mcp', 'what': 'Jira and Confluence'},
    'vercel': {'name': 'Vercel', 'url': 'https://mcp.vercel.com', 'what': 'Projects, deployments, logs'},
    'axiom': {'name': 'Axiom', 'url': 'https://mcp.axiom.co/mcp', 'what': 'Logs, traces, datasets (APL queries)'},
}
NAME_RE = re.compile(r'^[a-z][a-z0-9-]{1,30}$')
RESERVED = {'playwright', 'github'}
URL_RE = re.compile(r'https://\S+')
LOCAL_CALLBACK_RE = re.compile(r'^(https?://)?(localhost|127\.0\.0\.1):\d+/\S+$')


def load():
    try:
        with open(STORE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save(d):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    with open(STORE, 'w') as f:
        json.dump(d, f, indent=1)
    os.chmod(STORE, 0o600)
    write_codex_block(d)


def write_codex_block(d):
    """Codex reads MCP servers from config.toml; ours live in one managed block."""
    cfg = os.path.join(HOME, '.codex', 'config.toml')
    text = pathlib.Path(cfg).read_text() if os.path.exists(cfg) else ''
    text = re.sub(r'\n?# BEGIN agent-connections.*?# END agent-connections\n?', '\n', text, flags=re.S)
    block = ['# BEGIN agent-connections (managed by the Accounts page; edits are overwritten)']
    for name, s in sorted(d.items()):
        block.append(f'[mcp_servers.{name}]')
        if s.get('shared'):
            block += [
                f'command = {json.dumps(MCP_REMOTE)}',
                f'args = {json.dumps([s["url"]])}',
                'startup_timeout_sec = 60',
            ]
        else:
            block += [
                f'url = {json.dumps(s["url"])}',
                f'http_headers = {{ "Authorization" = {json.dumps(s["header"])} }}',
            ]
        block.append('')
    block.append('# END agent-connections')
    with open(cfg, 'w') as f:
        f.write(text.rstrip() + '\n\n' + '\n'.join(block) + '\n')


def _claude_add(name, cfg):
    run(f'claude mcp remove {name} -s user')
    rc, out = run(f'claude mcp add-json {name} {sh_quote(json.dumps(cfg))} -s user')
    return rc == 0, out


def register_token(name, url, header, who):
    """A server that takes a bearer token (GitHub)."""
    d = load()
    d[name] = {'url': url, 'header': header, 'who': who}
    save(d)
    return _claude_add(name, {'type': 'http', 'url': url, 'headers': {'Authorization': header}})


def unregister(name):
    d = load()
    d.pop(name, None)
    save(d)
    run(f'claude mcp remove {name} -s user')


def add_shared(name, url):
    d = load()
    d[name] = {'url': url, 'shared': True}
    save(d)
    return _claude_add(name, {'type': 'stdio', 'command': MCP_REMOTE, 'args': [url]})


def token_works(url, header):
    """True if the MCP server accepts the credential (initialize handshake)."""
    body = json.dumps(
        {
            'jsonrpc': '2.0',
            'id': 1,
            'method': 'initialize',
            'params': {
                'protocolVersion': '2025-06-18',
                'capabilities': {},
                'clientInfo': {'name': 'accounts-check', 'version': '1'},
            },
        }
    ).encode()
    code, _ = http(
        url,
        {'Authorization': header, 'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'},
        body,
    )
    return code == 200


def _token_files(url):
    key = hashlib.md5(url.encode()).hexdigest()
    return glob.glob(os.path.join(MCP_AUTH, 'mcp-remote-*', f'{key}_*'))


def signed_in(name):
    s = load().get(name)
    return bool(s) and any(f.endswith('_tokens.json') for f in _token_files(s['url']))


def flow(name):
    return f'mcp-{name}'


def start_login(name):
    start_session(flow(name), f'BROWSER=true {MCP_REMOTE_CLIENT} {sh_quote(load()[name]["url"])}')


def login_state(name):
    scr = screen(flow(name)) if active(flow(name)) else ''
    urls = [u.rstrip('.,)') for u in URL_RE.findall(scr) if 'authorize' in u or 'oauth' in u]
    ok = signed_in(name) and bool(scr)
    finished = ok or '[login finished]' in scr
    url = urls[0] if urls else ''
    return {'active': active(flow(name)), 'url': url, 'finished': finished, 'ok': ok, 'screen': scr[-3000:]}


def remove(name):
    """Sign out (drop the shared token) and unregister."""
    stop_session(flow(name))
    s = load().get(name)
    for f in _token_files(s['url']) if s else []:
        os.remove(f)
    unregister(name)


def servers():
    """Catalog entries plus any server added by URL, in page order: {key: {name, url, what, added}}."""
    d = load()
    out = {k: {**v, 'added': k in d} for k, v in CATALOG.items()}
    for k, v in d.items():
        if (v.get('shared') or v.get('oauth')) and k not in out:
            out[k] = {'name': k, 'url': v['url'], 'what': urlparse(v['url']).netloc, 'added': True}
    return out


def add_custom(name, url):
    """-> error message, or '' after adding and starting its sign-in."""
    if not NAME_RE.match(name) or name in RESERVED or name in CATALOG:
        return 'Name: 2-31 lowercase letters, digits or dashes, starting with a letter (not playwright/github).'
    if not re.match(r'^https://\S+$', url):
        return 'The address must start with https://'
    ok, out = add_shared(name, url)
    if not ok:
        return f'Could not add {name}: {out[:200]}'
    start_login(name)
    return ''


def migrate():
    """Connectors added before the shared sign-in (separate Claude/Codex logins) become shared."""
    for name, s in list(load().items()):
        if s.get('oauth') and not s.get('shared'):
            run(f'claude mcp logout {name}')
            run(f'codex mcp logout {name}')
            add_shared(name, s['url'])
