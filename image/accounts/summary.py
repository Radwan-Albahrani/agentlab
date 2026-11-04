"""/api/summary: what the hub shows on this agent's card (the shape is a contract with hub/)."""

import json
import os

import connectors
import onboarding
import pairing
import signin
from util import AGENT_ID, AGENT_OWNER, active, browser_up

CGROUP = '/sys/fs/cgroup'
THROTTLE_STATUS = '/home/agent/.local/state/agent-throttle/status.json'  # written by the host throttle broker
MB = 2**20


def heavy_jobs():
    try:
        with open(THROTTLE_STATUS) as f:
            status = json.load(f)
    except (OSError, ValueError):
        return [], []
    return status.get('running', []), status.get('waiting', [])


def _read(name):
    with open(os.path.join(CGROUP, name)) as f:
        return f.read()


def memory():
    """-> (used MB without file cache, limit MB or None)."""
    try:
        stat = dict(line.split() for line in _read('memory.stat').splitlines())
        used = int(_read('memory.current')) - int(stat.get('active_file', 0)) - int(stat.get('inactive_file', 0))
        limit = _read('memory.max').strip()
    except (OSError, ValueError):
        return None, None
    return used // MB, int(limit) // MB if limit.isdigit() else None


def resources():
    used, limit = memory()
    running, waiting = heavy_jobs()
    return {'usedMB': used, 'limitMB': limit, 'running': running, 'waiting': waiting, 'paused': 0}


def summary():
    accounts = {}
    for flow in signin.FLOWS:
        ok, detail = signin.status(flow)
        accounts[flow] = {'signedIn': ok, 'detail': detail, 'active': active(flow)}
    conns = {
        k: {'name': s['name'], 'added': s['added'], 'signedIn': s['added'] and connectors.signed_in(k)}
        for k, s in connectors.servers().items()
    }
    return {
        'agent': AGENT_ID,
        'owner': AGENT_OWNER,
        'accounts': accounts,
        'connectors': conns,
        'devices': len(pairing.devices()),
        'onboarded': onboarding.state()['done'],
        'resources': resources(),
        'browserUp': browser_up(),
    }
