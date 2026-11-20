"""cluster.json as agentctl rendered it (agents, companions, limits, domain), links to agents, and their Accounts API."""

import contextvars
import json
import os
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import quote

CONFIG = os.environ.get('HUB_CONFIG', '/etc/agentlab/cluster.json')
AGENT_URL = os.environ.get('HUB_AGENT_URL', '')  # '...{id}...' template
ACCOUNTS_PORT = 8790
ACCOUNTS = {'claude': 'Claude', 'codex': 'Codex', 'github': 'GitHub'}
HOSTNAME = re.compile(r'^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$')
# Tests point this at <folder>/<id>; otherwise each agent's own path, under the storage root the hub mounts whole
# (so adding or removing an agent never restarts the hub).
AGENTS_DIR = os.environ.get('AGENTS_DIR', '')
_cache: dict[str, Any] = {'mtime': None, 'data': {}}
_host: contextvars.ContextVar[str] = contextvars.ContextVar('request_host', default='')


def load() -> dict[str, Any]:
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


def agents() -> dict[str, dict[str, Any]]:
    return {a['id']: a for a in load().get('agents') or [] if a.get('id')}


def agent_dir(agent_id: str) -> str:
    if AGENTS_DIR:
        return os.path.join(AGENTS_DIR, agent_id)
    return (agents().get(agent_id) or {}).get('path') or os.path.join('/nonexistent', agent_id)


def ids() -> list[str]:
    return list(agents())


def domain() -> str:
    return load().get('domain') or ''


def use_host(header: str | None) -> None:
    """Remember the request's host (from its Host header) for published-port links; anything odd is ignored."""
    host = (header or '').strip().lower().rsplit(':', 1)[0] if ']' not in (header or '') else ''
    _host.set(host if HOSTNAME.match(host) else '')


def request_host() -> str:
    return _host.get()


def published(agent_id: str) -> dict[str, int]:
    """{tool: host port} this agent's tools are published on."""
    return (agents().get(agent_id) or {}).get('publish') or {}


def link(agent_id: str, path: str = '/') -> str:
    """Opens `path` (on the cluster domain) as agent `agent_id`, through the gate's view switch."""
    return f'https://{domain()}/_agentlab/view/{quote(agent_id, safe="")}?next={quote(path, safe="/")}'


def links(agent_id: str) -> dict[str, str]:
    out = {
        'chat': link(agent_id, '/'),
        'accounts': link(agent_id, '/_agentlab/accounts/'),
        'terminal': link(agent_id, '/_agentlab/terminal/'),
        'files': link(agent_id, '/_agentlab/files/'),
        'browser': link(agent_id, '/_agentlab/accounts/browser'),
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
            out['accounts'] = f'/agents/{quote(agent_id, safe="")}/accounts'
    return out


def accounts_url(agent_id: str) -> str:
    if AGENT_URL:
        return AGENT_URL.format(id=agent_id)
    upstream = (agents().get(agent_id) or {}).get('upstream') or f'http://agent-{agent_id}'
    return f'{upstream}:{ACCOUNTS_PORT}'


def owner(agent_id: str) -> str:
    return ((agents().get(agent_id) or {}).get('owner') or '').lower()


def owners() -> dict[str, list[str]]:
    """{owner email: [their agent ids]}"""
    out: dict[str, list[str]] = {}
    for a in agents().values():
        out.setdefault((a.get('owner') or '').lower(), []).append(a['id'])
    return out


def storage_mode() -> str:
    """'shared' (one pool for every agent) or 'per-person' (each owner's agents share a disk of their own)."""
    return (load().get('storage') or {}).get('mode') or 'shared'


def companions() -> dict[str, str]:
    """{companion name: agent id}"""
    return {c['name']: c.get('agent', '') for c in load().get('companions') or [] if c.get('name')}


def display_name(name: str) -> str:
    c: dict[str, Any] = next((c for c in load().get('companions') or [] if c.get('name') == name), {})
    return c.get('display_name') or name.capitalize()


def extra_stacks() -> list[str]:
    """Non-agentlab compose projects shown on Services (restart and logs only)."""
    return list((load().get('hub') or {}).get('extra_stacks') or [])


def auth() -> dict[str, Any]:
    return load().get('auth') or {}


def data_dir() -> str:
    return load().get('data') or '/srv/agentlab'


def size_mb(text: object) -> int | None:
    """'96g' / '512m' / '1t' -> MB; None when unreadable."""
    m = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*([kmgt]?)i?b?\s*', str(text or '').lower())
    if not m:
        return None
    return int(float(m[1]) * {'k': 1 / 1024, '': 1 / 2**20, 'm': 1, 'g': 1024, 't': 2**20}[m[2]])


def pool_mb() -> int:
    """Memory for all agents together (agentlab.slice MemoryMax)."""
    return size_mb((load().get('limits') or {}).get('total_memory')) or 0


def call(agent_id: str, path: str, body: Any = None, timeout: float = 60) -> tuple[int, Any]:
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
    except Exception:
        return 502, None
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, None


def summary(agent_id: str) -> Any:
    status, out = call(agent_id, '/api/summary')
    return out if status == 200 else None


def summaries(names: list[str]) -> dict[str, Any]:
    if not names:
        return {}
    with ThreadPoolExecutor(len(names)) as ex:
        return dict(zip(names, ex.map(summary, names), strict=True))
