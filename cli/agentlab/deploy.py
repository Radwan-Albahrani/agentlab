"""Getting rendered stacks running: networks, deploys (plain Compose or Coolify), and the edge and hub joining every
agent's network. Only stacks whose compose file changed since their last deploy are redeployed."""

import hashlib
import json
import os

from . import coolify, render
from .util import Failed, run, say, warn

LABEL = 'io.agentlab.cluster'


def rendered(cfg, *parts):
    return os.path.join(cfg['data'], 'rendered', *parts)


def stack_folder(cfg, stack):
    return rendered(cfg, 'compose', stack)


def compose_file(cfg, stack):
    return os.path.join(stack_folder(cfg, stack), 'docker-compose.yml')


def _digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _marker(cfg, stack):
    return os.path.join(stack_folder(cfg, stack), '.deployed')


def changed_since_deploy(cfg, stack, text):
    try:
        with open(_marker(cfg, stack)) as f:
            return f.read().strip() != _digest(text)
    except OSError:
        return True


def mark_deployed(cfg, stack, text):
    with open(_marker(cfg, stack), 'w') as f:
        f.write(_digest(text))


def networks(cfg):
    """[(network, bridge interface, subnet)]: the edge's and one per agent."""
    return [(render.EDGE_NETWORK, render.EDGE_BRIDGE, render.EDGE_SUBNET)] + [
        (render.network(a['id']), render.bridge(a['id']), a['subnet']) for a in cfg['agents']
    ]


def ensure_networks(cfg, plan):
    """Fixed subnets, so each agent keeps the address the firewall rules name. Others joining an agent's network
    get addresses from the upper half; the agent is always .2."""
    for name, bridge, subnet in networks(cfg):
        rc, out = run(
            ['docker', 'network', 'inspect', '-f', '{{range .IPAM.Config}}{{.Subnet}} {{end}}', name], check=False
        )
        if rc == 0:
            if subnet not in out.split():
                warn(
                    f'network {name} exists with subnet {out.strip() or "?"}, not {subnet}: remove it (its '
                    'containers first) and apply again, or the firewall rules miss this agent'
                )
            continue
        base = subnet.rsplit('.', 1)[0]
        plan.do(
            f'create network {name} ({subnet})',
            [
                'docker',
                'network',
                'create',
                '--label',
                f'{LABEL}={cfg["name"]}',
                '--subnet',
                subnet,
                '--gateway',
                f'{base}.1',
                '--ip-range',
                f'{base}.128/25',
                '-o',
                f'com.docker.network.bridge.name={bridge}',
                name,
            ],
        )


def project(cfg, stack):
    """The Compose project name Docker labels the stack's containers with (Coolify uses its service uuid)."""
    if cfg['deploy'] == 'coolify':
        return coolify.stack_uuid(stack_folder(cfg, stack)) or stack
    return stack


def containers(cfg, stack, service=None, all_states=False):
    cmd = ['docker', 'ps', '-q', '--filter', f'label=com.docker.compose.project={project(cfg, stack)}']
    if service:
        cmd += ['--filter', f'label=com.docker.compose.service={service}']
    if all_states:
        cmd.insert(2, '-a')
    return run(cmd, check=False)[1].split()


def deploy(cfg, stack, kind, key, plan, force=False):
    """Bring one stack up to its rendered file; True when it was (or would be) deployed."""
    path = compose_file(cfg, stack)
    with open(path) as f:
        text = f.read()
    # Stopped containers count as deployed: a companion down on purpose (not configured yet, or stopped by its agent)
    # must not be started again by every apply.
    if not force and not changed_since_deploy(cfg, stack, text) and containers(cfg, stack, all_states=True):
        return False
    if cfg['deploy'] == 'compose':
        plan.do(f'deploy {stack}', ['docker', 'compose', '-p', stack, '-f', path, 'up', '-d', '--remove-orphans'])
    else:
        api = coolify.Api(cfg)
        plan.do(
            f'deploy {stack} through Coolify',
            fn=lambda: coolify.deploy(api, cfg, stack, kind, key, stack_folder(cfg, stack), text),
        )
    if not plan.dry:
        mark_deployed(cfg, stack, text)
    return True


def connect(cfg, plan):
    """The edge, gate and hub must reach every agent. `docker network connect` is lost when Coolify or Compose
    recreates them, so this runs after every apply (and the watcher repeats it)."""
    for service, alias in (('edge', None), ('gate', 'gate'), ('hub', 'hub')):
        for cid in containers(cfg, 'agentlab-core', service):
            joined = json.loads(run(['docker', 'inspect', '-f', '{{json .NetworkSettings.Networks}}', cid])[1] or '{}')
            for a in cfg['agents']:
                net = render.network(a['id'])
                if net not in joined:
                    cmd = ['docker', 'network', 'connect', *(['--alias', alias] if alias else []), net, cid]
                    plan.do(f'connect {service} to {net}', cmd)


def stop(cfg, stack, plan):
    if cfg['deploy'] == 'coolify' and coolify.stack_uuid(stack_folder(cfg, stack)):
        uuid = coolify.stack_uuid(stack_folder(cfg, stack))
        plan.do(f'stop {stack}', fn=lambda: coolify.Api(cfg).call('POST', f'/services/{uuid}/stop'))
    else:
        plan.do(f'stop {stack}', ['docker', 'compose', '-p', stack, '-f', compose_file(cfg, stack), 'stop'])


def start(cfg, stack, plan):
    if cfg['deploy'] == 'coolify' and coolify.stack_uuid(stack_folder(cfg, stack)):
        uuid = coolify.stack_uuid(stack_folder(cfg, stack))
        plan.do(f'start {stack}', fn=lambda: coolify.Api(cfg).call('POST', f'/services/{uuid}/start'))
    else:
        plan.do(f'start {stack}', ['docker', 'compose', '-p', stack, '-f', compose_file(cfg, stack), 'up', '-d'])


def remove(cfg, stack, plan):
    """Stop and delete a stack's containers (never its data: volumes are bind mounts on the agent's disk)."""
    folder = stack_folder(cfg, stack)
    uuid = coolify.stack_uuid(folder) if cfg['deploy'] == 'coolify' else None
    if uuid:
        api = coolify.Api(cfg)
        plan.do(
            f'delete Coolify service {stack}', fn=lambda: api.call('DELETE', f'/services/{uuid}?delete_volumes=false')
        )
    elif os.path.isfile(compose_file(cfg, stack)):
        plan.do(f'remove {stack}', ['docker', 'compose', '-p', stack, '-f', compose_file(cfg, stack), 'down'])
    elif containers(cfg, stack, all_states=True):
        warn(f'{stack} has containers but no compose file; remove them with docker rm')
    if os.path.isdir(folder):
        plan.do(f'remove {folder}', fn=lambda: _rmtree(folder))


def _rmtree(folder):
    for name in os.listdir(folder):
        os.remove(os.path.join(folder, name))
    os.rmdir(folder)


def remove_network(name, plan):
    if run(['docker', 'network', 'inspect', name], check=False)[0] == 0:
        plan.do(f'remove network {name}', fn=lambda: _disconnect_and_remove(name))


def _disconnect_and_remove(name):
    info = json.loads(run(['docker', 'network', 'inspect', name])[1])[0]
    for cid in info.get('Containers') or {}:
        run(['docker', 'network', 'disconnect', '-f', name, cid], check=False)
    rc, out = run(['docker', 'network', 'rm', name], check=False)
    if rc:
        raise Failed(f'could not remove network {name}: {out}')


def orphans(cfg):
    """Rendered stacks no longer in the config (an agent or companion removed by hand from cluster.toml)."""
    folder = rendered(cfg, 'compose')
    known = set(render.stacks(cfg))
    found = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
    out = [s for s in found if s not in known]
    for s in out:
        say(f'  {s} is no longer in cluster.toml: `agentctl agent remove` cleans it up, or remove it by hand')
    return out
