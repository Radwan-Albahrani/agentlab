import json
import os
from typing import NotRequired, TypedDict

from . import deploy, disks, privileges, template, update
from .config import Cluster
from .util import Json, Needs, is_root, load_json, run, say


class ContainerState(TypedDict):
    state: str  # Docker's State.Status (running, exited, …), or 'absent'
    health: str  # Docker's State.Health.Status, or ''
    container: str


class OwnStatus(TypedDict, total=False):
    status: str  # the companion's own status.json state
    error: str


class AgentStatus(ContainerState):
    id: str
    owner: str
    memory_limit: str
    disk_used_gib: float | None
    disk_size_gib: float | None
    memory: NotRequired[str]  # filled in once docker stats has run


class CompanionStatus(ContainerState, OwnStatus):
    name: str
    agent: str


class Status(TypedDict):
    core: dict[str, str]  # service -> 'running healthy', 'absent', …
    agents: list[AgentStatus]
    companions: list[CompanionStatus]
    update: NotRequired[update.Record]
    companion_templates: NotRequired[Json]  # template's state file: companion name -> its template record


def _state(cfg: Cluster, stack: str, service: str) -> ContainerState:
    ids = deploy.containers(cfg, stack, service, all_states=True)
    if not ids:
        return {'state': 'absent', 'health': '', 'container': ''}
    info = json.loads(run(['docker', 'inspect', ids[0]])[1])[0]['State']
    return {
        'state': info.get('Status', ''),
        'health': (info.get('Health') or {}).get('Status', ''),
        'container': ids[0],
    }


def _memory(ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    out = run(['docker', 'stats', '--no-stream', '--format', '{{.ID}}\t{{.MemUsage}}', *ids], check=False)[1]
    return {line.split('\t')[0]: line.split('\t')[1] for line in out.splitlines() if '\t' in line}


def collect(cfg: Cluster) -> Status:
    core = {svc: _state_of(cfg, svc) for svc in ('edge', 'gate', 'hub')}
    agents: list[AgentStatus] = []
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
    companions: list[CompanionStatus] = [
        {
            'name': c['name'],
            'agent': c['agent'],
            **_state(cfg, f'agentlab-companion-{c["name"]}', 'companion'),
            **_own_status(paths.get(c['agent']), c['name']),
        }
        for c in cfg['companions']
    ]
    return {'core': core, 'agents': agents, 'companions': companions}


def _own_status(path: str | None, name: str) -> OwnStatus:
    """The companion's status.json; an exited container that isn't configured yet is waiting, not broken."""
    try:  # an agent-owned file: never follow a symlink there as root
        fd = os.open(f'{path}/workspace/.companion/{name}/status.json', os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as f:
            own = json.load(f)
    except (OSError, ValueError, TypeError):
        return {}
    return {'status': own.get('state', ''), 'error': own.get('error') or ''}


def _state_of(cfg: Cluster, service: str) -> str:
    ids = deploy.containers(cfg, 'agentlab-core', service, all_states=True)
    if not ids:
        return 'absent'
    return run(
        ['docker', 'inspect', '-f', '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}', ids[0]]
    )[1].strip()


def show(cfg: Cluster) -> Status:
    if not is_root() and not privileges.docker_ok():
        e = Needs(
            'status reads Docker, which this user cannot reach: run `sudo agentctl status` (or join the docker group)'
        )
        e.result = {'needs': 'sudo', 'command': 'sudo agentctl status'}
        raise e
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
    last = s['update'] = update.last(cfg)
    if last:
        later = f'; waiting: {", ".join(last["agents_deferred"])}' if last.get('agents_deferred') else ''
        err = f': {last["error"]}' if last.get('error') else ''
        say(f'  update {last.get("at", "?")} {last.get("result", "?")}{err} ({last.get("commit", "")}){later}')
    s['companion_templates'] = load_json(template.state_path(cfg), {}) or {}
    for line in template.summary(cfg):
        say(f'  companion {line}')
    return s
