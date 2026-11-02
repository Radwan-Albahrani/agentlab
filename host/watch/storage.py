"""Disk usage for the hub's Storage screen: every storage unit (the shared pool image, each person's image, or the
host's filesystem for a plain folder), an event when one fills past 80 / 90 / 95 %, and a per-folder breakdown of
each agent (du at idle IO priority, in its own systemd unit) every few hours or on request."""

import os
import sys
import time

import cluster

from . import host, store
from .settings import ALERT_LEVELS, DATA, REARM_BELOW, SCAN_EVERY_S, SCAN_MIN_BYTES

SCAN_UNIT = 'agentlab-watch-scan'
PACKAGE_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # host/, so `-m watch` resolves


def usage(path):
    """{size, used, avail} in bytes, or None when nothing is mounted there."""
    if not os.path.ismount(path):
        return None
    s = os.statvfs(path)
    size = s.f_blocks * s.f_frsize
    return {'size': size, 'used': size - s.f_bfree * s.f_frsize, 'avail': s.f_bavail * s.f_frsize}


def host_usage(path):
    """Like usage(), for the filesystem holding path (mounted or not)."""
    s = os.statvfs(path if os.path.exists(path) else '/')
    size = s.f_blocks * s.f_frsize
    return {'size': size, 'used': size - s.f_bfree * s.f_frsize, 'avail': s.f_bavail * s.f_frsize}


def crossed(pct):
    return max((level for level in ALERT_LEVELS if pct >= level), default=0)


def alert_change(pct, alerted):
    """('up', level) when a new level is crossed, ('down', level) when usage fell well below the last alert,
    else None. `alerted` is the level last alerted (0 = none)."""
    level = crossed(pct)
    if level > alerted:
        return 'up', level
    if alerted and pct < alerted - REARM_BELOW:
        return 'down', level
    return None


def agents():
    return [a for a in cluster.load().get('agents') or [] if a.get('id') and a.get('path')]


def _alert(state, key, label, use):
    pct = 100 * use['used'] / use['size'] if use and use['size'] else 0
    alerted = state.setdefault('alerted', {})
    change = alert_change(pct, alerted.get(key, 0))
    if change and change[0] == 'up':
        store.event('alert', f'💾 {label} {pct:.0f}% full', f'{use["avail"] / 1e9:.0f} GB left', ok=False)
    elif change:
        store.event('alert', f'{label} back to {pct:.0f}%')
    if change:
        alerted[key] = change[1]


def check(state):
    units = {}  # storage unit path -> usage (None while an image isn't mounted)
    for a in agents():
        unit = a.get('storage_unit') or ''
        if unit and unit not in units:
            units[unit] = usage(unit)
    disks = {a['id']: units[a['storage_unit']] if a.get('storage_unit') else host_usage(a['path']) for a in agents()}
    per_person = (cluster.load().get('storage') or {}).get('mode') == 'per-person'
    # pool: what the shared agents live on (the pool image, else the host's disk); per person: the host's disk, and
    # people: each owner's own image. disks: what each agent lives on, either way.
    people = {a['owner'].lower(): disks[a['id']] for a in agents() if a.get('owner')} if per_person else {}
    pool = host_usage(DATA) if per_person or not units else next(iter(units.values()))
    snapshot = store.load('usage.json', {})
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
    if time.time() - (snapshot.get('scan') or {}).get('at', 0) > SCAN_EVERY_S:
        start_scan()


def start_scan():
    """Run the breakdown as its own low-priority unit: du over every agent disk takes a while."""
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


def breakdown(du_output, agent, base):
    """Rows of the per-folder breakdown from `du -xb --max-depth=2 <base>` (the agent's total has path '')."""
    rows = []
    for line in du_output.splitlines():
        size, _, folder = line.partition('\t')
        if not folder or not size.isdigit():
            continue
        rel = os.path.relpath(folder, base)
        if int(size) >= SCAN_MIN_BYTES or rel == '.':
            rows.append({'agent': agent, 'path': '' if rel == '.' else rel, 'bytes': int(size)})
    return rows


def scan():
    started = time.time()
    items = []
    for a in agents():
        if os.path.isdir(a['path']):
            _, out = host.run(['du', '-xb', '--max-depth=2', a['path']], timeout=1800)
            items += breakdown(out, a['id'], a['path'])
    took = round(time.time() - started)
    snapshot = store.load('usage.json', {})
    snapshot['scan'] = {'at': time.time(), 'took': took, 'items': items}
    store.dump('usage.json', snapshot)
    store.event('scan', 'Storage breakdown updated', f'took {took} s')
