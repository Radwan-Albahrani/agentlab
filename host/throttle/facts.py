"""Live memory, memory-pressure and disk-pressure facts the throttle admits against."""

import json
import os
import subprocess
import time

from .settings import POOL_CGROUP
from .spool import homes

MiB = 2**20
MemoryUse = tuple[int, int]  # (used, limit) MB
_scopes: dict[str, str] = {}  # agent -> its container's cgroup
_resolved_at = 0.0


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _usage(cgroup: str) -> MemoryUse:
    """(used, hard limit) in MB; page cache doesn't count as used."""
    stat = dict(line.split() for line in _read(f'{cgroup}/memory.stat').splitlines())
    used = int(_read(f'{cgroup}/memory.current')) - int(stat.get('file', 0))
    return used // MiB, int(_read(f'{cgroup}/memory.max')) // MiB


def pool_mb() -> MemoryUse:
    return _usage(POOL_CGROUP)


def agent_mb(agent: str) -> MemoryUse | None:
    """(used, limit) of one agent's container, or None while it isn't running."""
    scope = _agent_scopes().get(agent)
    try:
        return _usage(scope) if scope else None
    except FileNotFoundError:
        return None


def _pressure(kind: str) -> float:
    """PSI "some" avg10, %."""
    some = _read(f'/proc/pressure/{kind}').splitlines()[0]
    return float(some.split('avg10=')[1].split()[0])


def io_pressure() -> float:
    return _pressure('io')


def memory_pressure() -> float:
    return _pressure('memory')


def _agent_scopes() -> dict[str, str]:
    """{agent: cgroup}; re-asks docker (slow) only when a container appeared or was replaced."""
    global _scopes, _resolved_at
    agents = set(homes())
    changed = not agents <= _scopes.keys() or any(not os.path.isdir(s) for s in _scopes.values())
    if changed and time.time() - _resolved_at > 60:
        _scopes, _resolved_at = _resolve_scopes(), time.time()
    return _scopes


def _docker(*args: str) -> str:
    return subprocess.run(['docker', *args], capture_output=True, text=True, check=False).stdout


def _resolve_scopes() -> dict[str, str]:
    ids = _docker('ps', '-q', '--no-trunc').split()
    if not ids:
        return {}
    containers = json.loads(_docker('inspect', *ids) or '[]')
    by_home = {home.rstrip('/'): aid for aid, home in homes().items()}
    scopes: dict[str, str] = {}
    for c in containers:
        home = next((m['Source'] for m in c['Mounts'] if m['Destination'] == '/home/agent'), None)
        scope = f'{POOL_CGROUP}/docker-{c["Id"]}.scope'
        if home and home.rstrip('/') in by_home and os.path.isdir(scope):
            scopes[by_home[home.rstrip('/')]] = scope
    return scopes
