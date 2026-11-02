"""The cluster as agentctl rendered it (cluster.json, mounted read-only): agents, companions, limits, the domain.
Each agent runs its Accounts app (JSON API) on :8790 inside its own network; the hub joins every agent network,
reads it and forwards the page's buttons to it.

People reach their own agent on the one cluster domain; an admin opens someone else's through the gate's
/_agentlab/view/<id> (it sets the view cookie, then goes to `next`), so every agent link below goes through it.
One-person setups may publish an agent's tools on host ports instead (cluster.json agents[].publish): then links go
straight to http://<the host this page was opened with>:<port>, the way people reach them."""

import contextvars
import json
import os
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

CONFIG = os.environ.get('HUB_CONFIG', '/etc/agentlab/cluster.json')
AGENT_URL = os.environ.get('HUB_AGENT_URL', '')  # '...{id}...' template; tests point it at fake agents
ACCOUNTS_PORT = 8790
ACCOUNTS = {'claude': 'Claude', 'codex': 'Codex', 'github': 'GitHub'}
HOSTNAME = re.compile(r'^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$')
_cache = {'mtime': None, 'data': {}}
_host = contextvars.ContextVar('request_host', default='')  # the host this request came in on, without its port


def load():
    """cluster.json, re-read when agentctl rewrites it (agents added or removed show up without a restart)."""
    try:
        mtime = os.path.getmtime(CONFIG)
    except OSError:
        return {}
    if mtime != _cache['mtime']:
        try:
            with open(CONFIG, encoding='utf-8') as f:
                _cache.update(mtime=mtime, data=json.load(f))
        except (OSError, ValueError):
            return _cache['data']
    return _cache['data']


def agents():
    """{id: agent} in config order."""
    return {a['id']: a for a in load().get('agents') or [] if a.get('id')}


def ids():
    return list(agents())


def domain():
    return load().get('domain') or ''


def use_host(header):
    """Remember the request's host (from its Host header) for published-port links; anything odd is ignored."""
    host = (header or '').strip().lower().rsplit(':', 1)[0] if ']' not in (header or '') else ''
    _host.set(host if HOSTNAME.match(host) else '')


def request_host():
    return _host.get()


def published(agent_id):
    """{tool: host port} this agent's tools are published on."""
    return (agents().get(agent_id) or {}).get('publish') or {}


def link(agent_id, path='/'):
    """Opens `path` (on the cluster domain) as agent `agent_id`, through the gate's view switch."""
    return f'https://{domain()}/_agentlab/view/{quote(agent_id, safe="")}?next={quote(path, safe="/")}'


def links(agent_id):
    out = {
        'chat': link(agent_id, '/'),
        'accounts': link(agent_id, '/_agentlab/accounts/'),
        'terminal': link(agent_id, '/_agentlab/terminal/'),
        'files': link(agent_id, '/_agentlab/files/'),
        'browser': link(agent_id, '/_agentlab/accounts/browser'),  # checks a browser is open, then the viewer
    }
    host, ports = request_host(), published(agent_id)
    if host:
        direct = {
            'chat': ('t3', '/'),
            'terminal': ('terminal', '/_agentlab/terminal/'),
            'files': ('files', '/_agentlab/files/'),
            'browser': ('browser', '/vnc.html?autoconnect=1&resize=remote'),
        }
        out.update({k: f'http://{host}:{ports[t]}{p}' for k, (t, p) in direct.items() if t in ports})
        if ports:
            out['accounts'] = f'/agents/{quote(agent_id, safe="")}/accounts'  # the hub's own page for it
    return out


def accounts_url(agent_id):
    if AGENT_URL:
        return AGENT_URL.format(id=agent_id)
    upstream = (agents().get(agent_id) or {}).get('upstream') or f'http://agent-{agent_id}'
    return f'{upstream}:{ACCOUNTS_PORT}'


def owner(agent_id):
    return ((agents().get(agent_id) or {}).get('owner') or '').lower()


def owners():
    """{owner email: [their agent ids]} in config order (one person may own several agents)."""
    out = {}
    for a in agents().values():
        out.setdefault((a.get('owner') or '').lower(), []).append(a['id'])
    return out


def storage_mode():
    """'shared' (one pool for every agent) or 'per-person' (each owner's agents share a disk of their own)."""
    return (load().get('storage') or {}).get('mode') or 'shared'


def companions():
    """{companion name: agent id}"""
    return {c['name']: c.get('agent', '') for c in load().get('companions') or [] if c.get('name')}


def display_name(name):
    """How a companion calls itself (cluster.json companions[].display_name), else its name capitalised."""
    c = next((c for c in load().get('companions') or [] if c.get('name') == name), {})
    return c.get('display_name') or name.capitalize()


def extra_stacks():
    """Compose projects that aren't agentlab's but are shown on Services (restart, logs; never deployed from here)."""
    return list((load().get('hub') or {}).get('extra_stacks') or [])


def auth():
    return load().get('auth') or {}


def data_dir():
    return load().get('data') or '/srv/agentlab'


def size_mb(text):
    """'96g' / '512m' / '1t' -> MB; None when unreadable."""
    m = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*([kmgt]?)i?b?\s*', str(text or '').lower())
    if not m:
        return None
    return int(float(m[1]) * {'k': 1 / 1024, '': 1 / 2**20, 'm': 1, 'g': 1024, 't': 2**20}[m[2]])


def pool_mb():
    """All agents together (agentlab.slice MemoryMax)."""
    return size_mb((load().get('limits') or {}).get('total_memory')) or 0


def call(agent_id, path, body=None, timeout=60):
    """(status, parsed JSON or None). body is sent as JSON with POST."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        accounts_url(agent_id) + path,
        data=data,
        method='POST' if data is not None else 'GET',
        headers={'Content-Type': 'application/json'},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    except Exception:  # agent stopped / starting
        return 502, None
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, None


def summary(agent_id):
    status, out = call(agent_id, '/api/summary')
    return out if status == 200 else None


def summaries(names):
    """{id: summary or None} for these agents, asked in parallel."""
    if not names:
        return {}
    with ThreadPoolExecutor(len(names)) as ex:
        return dict(zip(names, ex.map(summary, names), strict=True))
