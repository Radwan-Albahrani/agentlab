"""Live memory, swap and disk-pressure facts the throttle admits against."""

import json
import os
import subprocess
import time

from .settings import POOL_CGROUP
from .spool import homes

MiB = 2**20
_scopes, _resolved_at = {}, 0.0


def _read(path):
    with open(path) as f:
        return f.read()


def _usage(cgroup):
    """(used, hard limit) in MB; page cache doesn't count as used."""
    stat = dict(line.split() for line in _read(f'{cgroup}/memory.stat').splitlines())
    used = int(_read(f'{cgroup}/memory.current')) - int(stat.get('file', 0))
    return used // MiB, int(_read(f'{cgroup}/memory.max')) // MiB


def pool_mb():
    return _usage(POOL_CGROUP)


def agent_mb(agent):
    """(used, limit) of one agent's container, or None while it isn't running."""
    scope = _agent_scopes().get(agent)
    try:
        return _usage(scope) if scope else None
    except FileNotFoundError:
        return None


def io_pressure():
    """PSI io "some" avg10, %."""
    some = _read('/proc/pressure/io').splitlines()[0]
    return float(some.split('avg10=')[1].split()[0])


def swap_used_mb():
    kb = {
        key: int(value.split()[0])
        for key, value in (line.split(':', 1) for line in _read('/proc/meminfo').splitlines())
    }
    return (kb['SwapTotal'] - kb['SwapFree']) // 1024


def _agent_scopes():
    """{agent: cgroup}; re-asks docker (slow) only when a container appeared or was replaced."""
    global _scopes, _resolved_at
    agents = set(homes())
    changed = not agents <= _scopes.keys() or any(not os.path.isdir(s) for s in _scopes.values())
    if changed and time.time() - _resolved_at > 60:
        _scopes, _resolved_at = _resolve_scopes(), time.time()
    return _scopes


def _docker(*args):
    return subprocess.run(['docker', *args], capture_output=True, text=True, check=False).stdout


def _resolve_scopes():
    ids = _docker('ps', '-q', '--no-trunc').split()
    if not ids:
        return {}
    containers = json.loads(_docker('inspect', *ids) or '[]')
    by_home = {home.rstrip('/'): aid for aid, home in homes().items()}
    scopes = {}
    for c in containers:
        home = next((m['Source'] for m in c['Mounts'] if m['Destination'] == '/home/agent'), None)
        scope = f'{POOL_CGROUP}/docker-{c["Id"]}.scope'
        if home and home.rstrip('/') in by_home and os.path.isdir(scope):
            scopes[by_home[home.rstrip('/')]] = scope
    return scopes
