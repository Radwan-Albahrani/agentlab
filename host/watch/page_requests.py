"""The hub's buttons. The hub (in a container) drops requests/<action>~<target> files; the watcher, which can reach
Docker and systemd, carries them out within a second:
rescan · cleanup · restart~<container> · logs~<container> · deploy~<stack> · remove~companion~<name>.
The hub has already checked the person may do it; these checks keep a bad name from reaching a command line."""

import os
import re

import cluster

from . import host, storage, store
from .settings import AGENTCTL, LOG_TAIL_LINES

ACTIONS = ('rescan', 'cleanup', 'restart', 'logs', 'deploy', 'remove')
COMPANION = re.compile(r'^companion~([a-z0-9][a-z0-9-]{0,28}[a-z0-9])$')
STACK = re.compile(r'^agentlab-[a-z0-9-]+$')


def parse(filename):
    """(action, target) of a request file, or None if it isn't one."""
    action, _, target = filename.partition('~')
    if action not in ACTIONS:
        return None
    return action, target


def allowed(action, target, containers):
    """Restart and logs only for known containers; Coolify's own containers are never restarted from the hub;
    deploy only for agentlab's own stacks (the name ends up on agentctl's command line)."""
    if action in ('restart', 'logs'):
        known = containers.get(target) or {}
        # Only containers of agentlab's stacks and [hub] extra_stacks: anything else on the server stays out of reach.
        return bool(known.get('stack')) and (action == 'logs' or known['stack'] != 'coolify')
    if action == 'deploy':
        return bool(STACK.match(target))
    if action == 'remove':
        m = COMPANION.match(target)
        return bool(m) and any(c.get('name') == m.group(1) for c in cluster.load().get('companions') or [])
    return True


def _rescan(_target, _container):
    storage.start_scan()
    store.event('scan', 'Storage rescan requested from the hub')


def _cleanup(_target, _container):
    rc, out = host.start_unit('agentlab-janitor.service')
    store.event('cleanup', 'Cleanup started from the hub', '' if rc == 0 else out, ok=rc == 0)


def _restart(target, container):
    rc, out = host.run(['docker', 'restart', target])
    store.event('restart', f'{container["service"]} restarted from the hub', '' if rc == 0 else out[-200:], ok=rc == 0)


def _logs(target, _container):
    _, out = host.run(['docker', 'logs', '--tail', str(LOG_TAIL_LINES), '--timestamps', target])
    os.makedirs(store.path('logs'), exist_ok=True)
    with open(store.path('logs', target + '.txt'), 'w') as f:
        f.write(out[-200_000:])


def _deploy(target, _container):
    """The hub can't edit cluster.toml; a deploy re-applies it and forces this stack to be redeployed."""
    rc, out = host.run(['python3', AGENTCTL, 'apply', '--stack', target], timeout=1800)
    store.event('deploy', f'{target} deployed' if rc == 0 else f'{target} deploy failed', out[-400:], ok=rc == 0)


def _remove(target, _container):
    name = target.split('~', 1)[1]
    rc, out = host.run(['python3', AGENTCTL, 'companion', 'remove', '-', name], timeout=600)
    store.event(
        'companion', f'{name} removed from the hub' if rc == 0 else f'removing {name} failed', out[-400:], ok=rc == 0
    )


HANDLERS = {
    'rescan': _rescan,
    'cleanup': _cleanup,
    'restart': _restart,
    'logs': _logs,
    'deploy': _deploy,
    'remove': _remove,
}


def handle_pending():
    folder = store.path('requests')
    os.makedirs(folder, exist_ok=True)
    pending = sorted(os.listdir(folder))
    if not pending:
        return
    containers = {c['name']: c for c in store.load('containers.json', {}).get('items') or []}  # docker ps is slow
    for filename in pending:
        os.remove(os.path.join(folder, filename))
        request = parse(filename)
        if request and allowed(*request, containers):
            action, target = request
            HANDLERS[action](target, containers.get(target))
