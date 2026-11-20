"""Disk usage, fill alerts and per-folder breakdown for the hub's Storage screen."""

import json
import os
import sys
import time
from typing import Literal, TypedDict

import cluster

from . import host, store
from .settings import ALERT_LEVELS, DATA, REARM_BELOW, SCAN_EVERY_S, SCAN_MIN_BYTES

SCAN_UNIT = 'agentlab-watch-scan'
SCAN_DEPTH = 4  # deep enough to name what fills a folder (home/.local/share/docker)
PACKAGE_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Use(TypedDict):
    """A disk's size, used and avail bytes."""

    size: int
    used: int
    avail: int


class Row(TypedDict):
    """A breakdown row: a folder of an agent's and its bytes on disk."""

    agent: str
    path: str  # '' = the agent's total
    bytes: int


class Scan(TypedDict):
    at: float
    took: int  # seconds
    items: list[Row]
    units: dict[str, int]  # storage unit -> bytes used as the scan ended


class Usage(TypedDict, total=False):
    """usage.json: check() writes all but scan, scan() writes scan."""

    at: float
    disks: dict[str, Use | None]  # agent id ->
    people: dict[str, Use | None]  # owner email ->
    units: dict[str, Use | None]  # storage unit ->
    pool: Use | None
    scan: Scan


def usage(path: str) -> Use | None:
    """{size, used, avail} in bytes, or None when nothing is mounted there."""
    if not os.path.ismount(path):
        return None
    s = os.statvfs(path)
    size = s.f_blocks * s.f_frsize
    return {'size': size, 'used': size - s.f_bfree * s.f_frsize, 'avail': s.f_bavail * s.f_frsize}


def host_usage(path: str) -> Use:
    s = os.statvfs(path if os.path.exists(path) else '/')
    size = s.f_blocks * s.f_frsize
    return {'size': size, 'used': size - s.f_bfree * s.f_frsize, 'avail': s.f_bavail * s.f_frsize}


def crossed(pct: float) -> int:
    return max((level for level in ALERT_LEVELS if pct >= level), default=0)


def alert_change(pct: float, alerted: int) -> tuple[Literal['up', 'down'], int] | None:
    """('up' | 'down', level) or None; `alerted` is the level last alerted (0 = none)."""
    level = crossed(pct)
    if level > alerted:
        return 'up', level
    if alerted and pct < alerted - REARM_BELOW:
        return 'down', level
    return None


def agents() -> list[cluster.Agent]:
    return [a for a in cluster.load().get('agents') or [] if a.get('id') and a.get('path')]


def _alert(state: store.State, key: str, label: str, use: Use) -> None:
    pct = 100 * use['used'] / use['size'] if use and use['size'] else 0
    alerted = state.setdefault('alerted', {})
    change = alert_change(pct, alerted.get(key, 0))
    if change and change[0] == 'up':
        store.event('alert', f'💾 {label} {pct:.0f}% full', f'{use["avail"] / 1e9:.0f} GB left', ok=False)
    elif change:
        store.event('alert', f'{label} back to {pct:.0f}%')
    if change:
        alerted[key] = change[1]


def check(state: store.State) -> None:
    units: dict[str, Use | None] = {}  # path -> usage (None while unmounted)
    agent_list = agents()
    for a in agent_list:
        unit = a.get('storage_unit') or ''
        if unit and unit not in units:
            units[unit] = usage(unit)
    disks = {a['id']: units[a['storage_unit']] if a.get('storage_unit') else host_usage(a['path']) for a in agent_list}
    per_person = (cluster.load().get('storage') or cluster.Storage()).get('mode') == 'per-person'
    people = {a['owner'].lower(): disks[a['id']] for a in agent_list if a.get('owner')} if per_person else {}
    pool = host_usage(DATA) if per_person or not units else next(iter(units.values()))
    snapshot: Usage = store.load('usage.json', {})
    snapshot.update({'at': time.time(), 'disks': disks, 'people': people, 'units': units, 'pool': pool})
    store.dump('usage.json', snapshot)
    unmounted = sorted(u for u, use in units.items() if use is None)
    if unmounted and state.get('unmounted') != unmounted:
        store.event('alert', 'Storage not mounted: ' + ', '.join(unmounted), 'sudo agentctl apply', ok=False)
    state['unmounted'] = unmounted
    for unit, use in units.items():
        if use:
            _alert(state, unit, f'{os.path.basename(unit)} disk', use)
    _alert(state, '_server', 'Server disk', host_usage(DATA))
    scan = snapshot.get('scan')
    scanned = scan.get('at', 0) if scan else 0
    if time.time() - scanned > SCAN_EVERY_S or cleaned_since(scanned):
        start_scan()


def cleaned_since(at: float) -> bool:
    """Whether a cleanup finished after `at` (the janitor's closing event), so the breakdown is out of date."""
    try:
        with open(store.path('events.jsonl')) as f:
            tail = f.readlines()[-200:]
    except OSError:
        return False
    for line in reversed(tail):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get('at', 0) <= at:
            return False
        if e.get('kind') == 'cleanup' and str(e.get('title', '')).startswith(('Cleanup freed', 'Cleanup: ')):
            return True
    return False


def start_scan() -> None:
    if host.unit_active(SCAN_UNIT):
        return
    properties = ['IOSchedulingClass=idle', 'Nice=15', 'MemoryHigh=512M', f'WorkingDirectory={PACKAGE_PARENT}']
    command = [
        'systemd-run',
        '--unit',
        SCAN_UNIT,
        '--collect',
        '--setenv=PYTHONDONTWRITEBYTECODE=1',
        f'--setenv=AGENTLAB_CLUSTER={cluster.PATH}',
    ]
    for prop in properties:
        command += ['-p', prop]
    host.run(['systemctl', 'reset-failed', SCAN_UNIT])
    host.run([*command, sys.executable, '-m', 'watch', '--scan'])


def breakdown(du_output: str, agent: str, base: str) -> list[Row]:
    """Breakdown rows from `du -x -B1 --max-depth=N <base>` (space on disk); the agent's total has path ''."""
    rows: list[Row] = []
    for line in du_output.splitlines():
        size, _, folder = line.partition('\t')
        if not folder or not size.isdigit():
            continue
        rel = os.path.relpath(folder, base)
        if int(size) >= SCAN_MIN_BYTES or rel == '.':
            rows.append({'agent': agent, 'path': '' if rel == '.' else rel, 'bytes': int(size)})
    return rows


def scan() -> None:
    started = time.time()
    items: list[Row] = []
    for a in agents():
        if os.path.isdir(a['path']):
            _, out = host.run(['du', '-x', '-B1', f'--max-depth={SCAN_DEPTH}', a['path']], timeout=1800)
            items += breakdown(out, a['id'], a['path'])
    took = round(time.time() - started)
    snapshot: Usage = store.load('usage.json', {})
    # what each disk had in use as the scan ended, so the hub can tell growth since from the disk's own overhead
    units = {
        u: use['used'] for u, use in ((u, usage(u)) for u in {a.get('storage_unit') for a in agents()} if u) if use
    }
    snapshot['scan'] = {'at': time.time(), 'took': took, 'items': items, 'units': units}
    store.dump('usage.json', snapshot)
    store.event('scan', 'Storage breakdown updated', f'took {took} s')
