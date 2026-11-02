"""`agentctl status`: one screen of the cluster — each agent's container, memory and disk, plus the core."""

import json
import os

from . import deploy, disks
from .util import run, say


def _state(cfg, stack, service):
    ids = deploy.containers(cfg, stack, service, all_states=True)
    if not ids:
        return {'state': 'absent', 'health': '', 'container': ''}
    info = json.loads(run(['docker', 'inspect', ids[0]])[1])[0]['State']
    return {
        'state': info.get('Status', ''),
        'health': (info.get('Health') or {}).get('Status', ''),
        'container': ids[0],
    }


def _memory(ids):
    if not ids:
        return {}
    out = run(['docker', 'stats', '--no-stream', '--format', '{{.ID}}\t{{.MemUsage}}', *ids], check=False)[1]
    return {line.split('\t')[0]: line.split('\t')[1] for line in out.splitlines() if '\t' in line}


def collect(cfg):
    core = {svc: _state_of(cfg, svc) for svc in ('edge', 'gate', 'hub')}
    agents = []
    for a in cfg['agents']:
        st = _state(cfg, f'agentlab-agent-{a["id"]}', 'agent')
        use = disks.usage(a['storage_unit'] or a['path'])
        agents.append(
            {
                'id': a['id'],
                'owner': a['owner'],
                **st,
                'memory_limit': a['memory'],
                'disk_used_gib': round(use['used'] / 2**30, 1) if use else None,
                'disk_size_gib': round(use['size'] / 2**30, 1) if use else None,
            }
        )
    mem = _memory([x['container'] for x in agents if x['state'] == 'running'])
    for x in agents:
        x['memory'] = mem.get(x['container'][:12], '')
    paths = {a['id']: a['path'] for a in cfg['agents']}
    companions = [
        {
            'name': c['name'],
            'agent': c['agent'],
            **_state(cfg, f'agentlab-companion-{c["name"]}', 'companion'),
            **_own_status(paths.get(c['agent']), c['name']),
        }
        for c in cfg['companions']
    ]
    return {'core': core, 'agents': agents, 'companions': companions}


def _own_status(path, name):
    """What the companion says about itself (its launcher's status.json): a container that exited because it isn't
    configured yet is waiting for its secrets, not broken."""
    try:  # an agent-owned file: never follow a symlink there as root
        fd = os.open(f'{path}/workspace/.companion/{name}/status.json', os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as f:
            own = json.load(f)
    except (OSError, ValueError, TypeError):
        return {}
    return {'status': own.get('state', ''), 'error': own.get('error') or ''}


def _state_of(cfg, service):
    ids = deploy.containers(cfg, 'agentlab-core', service, all_states=True)
    if not ids:
        return 'absent'
    return run(
        ['docker', 'inspect', '-f', '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}', ids[0]]
    )[1].strip()


def show(cfg):
    s = collect(cfg)
    say(f'{cfg["name"]}  https://{cfg["domain"]}  hub https://{cfg["hub_domain"]}')
    say('  core: ' + '  '.join(f'{k} {v}' for k, v in s['core'].items()))
    for a in s['agents']:
        disk = f'{a["disk_used_gib"]}/{a["disk_size_gib"]} GiB' if a['disk_size_gib'] else 'missing'
        state = f'{a["state"]} {a["health"]}'.strip()
        say(f'  {a["id"]:<14} {state:<18} mem {a["memory"] or "-":<22} disk {disk:<16} {a["owner"]}')
    for c in s['companions']:
        own = f'  {c["status"]}' if c.get('status') else ''
        say(f'  companion {c["name"]:<10} {c["state"]} {c["health"]}{own}  (agent {c["agent"]})')
    return s
