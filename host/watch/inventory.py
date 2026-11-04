"""Every stack agentctl rendered and every container, each tagged with its stack, for the hub's Services and Configs
screens. Also keeps the edge, gate and hub joined to every agent network: `docker network connect` is undone whenever
Compose or Coolify recreates them, and without it agents become unreachable until the next `agentctl apply`."""

import json
import os
import time

import cluster

from . import host, store
from .settings import COMPOSE_DIR

PROJECT, SERVICE = 'com.docker.compose.project', 'com.docker.compose.service'
COOLIFY_PROJECT = 'coolify.projectName'  # Coolify names each service's Compose project by its uuid; this is the name


def stacks(root=COMPOSE_DIR):
    """[{id, uuid, file}] sorted by id; id is the stack name (agentlab-core, agentlab-agent-<id>, ...); uuid is the
    Coolify service uuid when Coolify deploys it, else ''."""
    out = []
    for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        file = os.path.join(root, name, 'docker-compose.yml')
        if not os.path.isfile(file):
            continue
        try:
            with open(os.path.join(root, name, '.coolify-service-uuid')) as f:
                uuid = f.read().strip()
        except OSError:
            uuid = ''
        out.append({'id': name, 'uuid': uuid, 'file': file})
    return out


def labels(text):
    return dict(part.split('=', 1) for part in (text or '').split(',') if '=' in part)


def tag(ps_lines, stack_list, extra=()):
    """Rows for containers.json from `docker ps --format '{{json .}}'` lines. `extra`: other projects the admin wants
    on the hub ([hub] extra_stacks), shown under that name (restart and logs only): a Compose project name, or a
    Coolify project name (which groups several Coolify services, e.g. "media")."""
    by_project = {s['id']: s['id'] for s in stack_list} | {s['uuid']: s['id'] for s in stack_list if s['uuid']}
    by_project |= {p: p for p in extra}
    rows = []
    for line in ps_lines:
        try:
            c = json.loads(line)
        except ValueError:
            continue
        name, lab = c.get('Names', ''), labels(c.get('Labels'))
        stack = by_project.get(lab.get(PROJECT, ''), '')
        if not stack and lab.get(COOLIFY_PROJECT) in extra:
            stack = lab[COOLIFY_PROJECT]
        if not stack and name.startswith('coolify'):
            stack = 'coolify'
        rows.append(
            {
                'name': name,
                'service': lab.get(SERVICE, name) if stack and stack != 'coolify' else name,
                'stack': stack,
                'state': c.get('State'),
                'status': c.get('Status'),
                'image': c.get('Image'),
                'created': c.get('CreatedAt'),
            }
        )
    return rows


def keep_connected(rows):
    """The edge, gate and hub must sit on every agent network (see the module docstring)."""
    nets = [f'agentlab-{a["id"]}' for a in cluster.load().get('agents') or []]
    for r in rows:
        if r['stack'] != 'agentlab-core' or r['service'] not in ('edge', 'gate', 'hub') or r['state'] != 'running':
            continue
        _, out = host.run(['docker', 'inspect', '-f', '{{json .NetworkSettings.Networks}}', r['name']])
        try:
            joined = json.loads(out or '{}')
        except ValueError:
            continue
        for net in nets:
            if net not in joined:
                alias = ['--alias', r['service']] if r['service'] != 'edge' else []
                rc, msg = host.run(['docker', 'network', 'connect', *alias, net, r['name']])
                agent = net.removeprefix('agentlab-')
                store.event(
                    'network',
                    f'{r["service"].capitalize()} reconnected to the {agent} agent',
                    'Restarting it drops the link to each agent; without it the agent would be unreachable.'
                    if rc == 0
                    else f'Could not reconnect: {msg[-200:]}',
                    ok=rc == 0,
                )


def extra_networks(networks, agent_id):
    """The networks an agent container should not be on: Coolify adds its own per-service network to every
    container it deploys, and the firewall only knows the agent's address on agentlab-<id>; through another network
    the agent could reach the host and the hub unchecked."""
    return sorted(n for n in networks if n != f'agentlab-{agent_id}')


def keep_isolated(rows):
    for r in rows:
        if not r['stack'].startswith('agentlab-agent-') or r['service'] != 'agent' or r['state'] != 'running':
            continue
        _, out = host.run(['docker', 'inspect', '-f', '{{json .NetworkSettings.Networks}}', r['name']])
        try:
            joined = json.loads(out or '{}')
        except ValueError:
            continue
        agent = r['stack'].removeprefix('agentlab-agent-')
        for net in extra_networks(joined, agent):
            rc, msg = host.run(['docker', 'network', 'disconnect', net, r['name']])
            store.event(
                'network',
                f'{agent} agent isolated again after a deploy',
                f'Coolify adds every container it deploys to a network of its own ({net}); taken off it, so the agent '
                'reaches only what its own network allows.'
                if rc == 0
                else f'Could not take it off {net}: {msg[-200:]}',
                ok=rc == 0,
            )


def check(_state):
    stack_list = stacks()
    _, out = host.run(['docker', 'ps', '-a', '--format', '{{json .}}'])
    rows = tag(out.splitlines(), stack_list, (cluster.load().get('hub') or {}).get('extra_stacks') or [])
    store.dump(
        'containers.json',
        {'at': time.time(), 'items': rows, 'stacks': [{'id': s['id'], 'uuid': s['uuid']} for s in stack_list]},
    )
    keep_connected(rows)
    keep_isolated(rows)
