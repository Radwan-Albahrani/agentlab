"""Networks and stack deploys (plain Compose or Coolify)."""

import datetime
import enum
import hashlib
import json
import os
import re
import subprocess
import time
from collections.abc import Callable, Collection, Iterable
from typing import TypedDict

from . import coolify, render
from .config import AgentCfg, Cluster
from .coolify import StackKind
from .util import Failed, Plan, run, say, warn

LABEL = 'io.agentlab.cluster'


class ContainerRow(TypedDict):
    """One row of `docker ps` for a stack; state and status are Docker's own words."""

    name: str
    state: str
    status: str
    service: str
    rendered: str


def rendered(cfg: Cluster, *parts: str) -> str:
    return os.path.join(cfg['data'], 'rendered', *parts)


def stack_folder(cfg: Cluster, stack: str) -> str:
    return rendered(cfg, 'compose', stack)


def compose_file(cfg: Cluster, stack: str) -> str:
    return os.path.join(stack_folder(cfg, stack), 'docker-compose.yml')


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _marker(cfg: Cluster, stack: str) -> str:
    return os.path.join(stack_folder(cfg, stack), '.deployed')


def changed_since_deploy(cfg: Cluster, stack: str, text: str) -> bool:
    try:
        with open(_marker(cfg, stack)) as f:
            return f.read().strip() != _digest(text)
    except OSError:
        return True


def mark_deployed(cfg: Cluster, stack: str, text: str) -> None:
    with open(_marker(cfg, stack), 'w') as f:
        f.write(_digest(text))


def networks(cfg: Cluster) -> list[tuple[str, str, str]]:
    """[(network, bridge interface, subnet)]: the edge's and one per agent."""
    return [(render.EDGE_NETWORK, render.EDGE_BRIDGE, render.EDGE_SUBNET)] + [
        (render.network(a['id']), render.bridge(a['id']), a['subnet']) for a in cfg['agents']
    ]


def ensure_networks(cfg: Cluster, plan: Plan) -> None:
    """Fixed subnets (the firewall names each agent's address); the agent is always .2."""
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


def project(cfg: Cluster, stack: str) -> str:
    if cfg['deploy'] == 'coolify':
        return coolify.stack_uuid(stack_folder(cfg, stack)) or stack
    return stack


def containers(cfg: Cluster, stack: str, service: str | None = None, all_states: bool = False) -> list[str]:
    cmd = ['docker', 'ps', '-q', '--filter', f'label=com.docker.compose.project={project(cfg, stack)}']
    if service:
        cmd += ['--filter', f'label=com.docker.compose.service={service}']
    if all_states:
        cmd.insert(2, '-a')
    return run(cmd, check=False)[1].split()


def stale_images(cfg: Cluster, stack: str) -> list[str]:
    """Image tags newer than what running containers use; compared by creation time, since ids never match under containerd."""
    out: set[str] = set()
    for cid in containers(cfg, stack):
        rc, info = run(['docker', 'inspect', '-f', '{{.Config.Image}} {{.Created}}', cid], check=False)
        if rc or len(info.split()) != 2:
            continue
        tag, started = info.split()
        rc, built = run(['docker', 'image', 'inspect', '-f', '{{.Created}}', tag], check=False)
        if rc == 0 and built.strip() and _when(built) > _when(started):
            out.add(tag)
    return sorted(out)


def _when(stamp: str) -> datetime.datetime:
    m = re.fullmatch(r'([\d-]+T[\d:]+)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)', stamp.strip())
    if not m:
        return datetime.datetime.min.replace(tzinfo=datetime.UTC)
    head, frac, zone = m.groups()
    zone = '+00:00' if zone == 'Z' else zone
    return datetime.datetime.fromisoformat(f'{head}.{(frac or "0")[:6].ljust(6, "0")}{zone}')


class T3(enum.Enum):
    """Why an agent gave no answer about its T3 chats."""

    STOPPED = 'its container is not running'
    UNREADABLE = 'agent-t3 failed or answered garbage'


ASK_T3_S = 60


def ask_t3(cfg: Cluster, agent: AgentCfg, question: str) -> object:
    """The agent's own answer about its T3 chats (`agent-t3 <question>` in its container, JSON), or why there is none.
    The host never opens the database itself: the agent's image carries the typed reader."""
    ids = containers(cfg, f'agentlab-agent-{agent["id"]}', 'agent')
    if not ids:
        return T3.STOPPED
    try:
        rc, out = run(['docker', 'exec', '-u', 'agent', ids[0], 'agent-t3', question], check=False, timeout=ASK_T3_S)
    except subprocess.TimeoutExpired:
        return T3.UNREADABLE
    if rc:
        return T3.UNREADABLE
    try:
        got: object = json.loads(out)
    except ValueError:
        return T3.UNREADABLE
    return got


def agent_busy(cfg: Cluster, agent: AgentCfg) -> bool:
    """Whether a T3 turn is in progress (no end time and no finished status); a stopped agent is idle, one that
    can't answer counts as busy."""
    got = ask_t3(cfg, agent, 'busy')
    if got is T3.STOPPED:
        return False
    return got if isinstance(got, bool) else True


def agent_of(cfg: Cluster, stack: str) -> AgentCfg | None:
    return next((a for a in cfg['agents'] if stack == f'agentlab-agent-{a["id"]}'), None)


def why_deploy(cfg: Cluster, stack: str, text: str, force: bool = False) -> tuple[str, str]:
    """(reason to deploy or '', skip message or ''); a changed image restarts an agent only while idle, unless --force."""
    if force:
        return 'asked for', ''
    if changed_since_deploy(cfg, stack, text):
        return 'its file changed', ''
    # Stopped containers count as deployed, so apply never restarts a companion stopped on purpose.
    if not containers(cfg, stack, all_states=True):
        return 'not running', ''
    stale = stale_images(cfg, stack)
    if not stale:
        return '', ''
    agent = agent_of(cfg, stack)
    if agent and agent_busy(cfg, agent):
        return '', f'{agent["id"]} busy (a T3 turn is running); its new image goes live on the next apply'
    return f'newer image: {", ".join(stale)}', ''


def deploy(cfg: Cluster, stack: str, kind: StackKind, key: str | None, plan: Plan, force: bool = False) -> bool:
    """Bring one stack up to its rendered file and current images; True when it was (or would be) deployed."""
    path = compose_file(cfg, stack)
    with open(path) as f:
        text = f.read()
    reason, skip = why_deploy(cfg, stack, text, force)
    if skip:
        say(f'  {skip}')
    if not reason:
        return False
    note = f' ({reason})' if reason.startswith('newer image') else ''
    if cfg['deploy'] == 'compose':
        plan.do(f'deploy {stack}{note}', ['docker', 'compose', '-p', stack, '-f', path, 'up', '-d', '--remove-orphans'])
    else:
        api = coolify.Api(cfg)
        plan.do(
            f'deploy {stack} through Coolify{note}',
            fn=lambda: coolify.deploy(api, cfg, stack, kind, key, stack_folder(cfg, stack), text),
        )
    if not plan.dry:
        DEPLOYED.add(stack)
        mark_deployed(cfg, stack, text)
        retry: Callable[[list[str]], None] | None = None
        if cfg['deploy'] == 'coolify':

            def redeploy(stuck: list[str]) -> None:
                for name in stuck:
                    force_remove(name)
                coolify.deploy(api, cfg, stack, kind, key, stack_folder(cfg, stack), text)

            retry = redeploy
        settle(cfg, stack, kind, text, on_stuck=retry)
        agent = agent_of(cfg, stack)
        if agent:  # the new container waits for this before its first downloads
            isolate(cfg, plan, [agent])
    return True


# Stacks deployed this run: a second Coolify deploy while the first still runs would race it.
DEPLOYED: set[str] = set()
SETTLE_S = 15 * 60
STUCK_S = 3 * 60  # no container of the new render while an old one still stands: Coolify couldn't replace it
LEFTOVER = re.compile(r'^[0-9a-f]{12}_')


def deployed_this_run(stack: str) -> bool:
    return stack in DEPLOYED


def settle(
    cfg: Cluster,
    stack: str,
    kind: StackKind,
    text: str,
    timeout_s: int = SETTLE_S,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
    on_stuck: Callable[[list[str]], None] | None = None,
) -> None:
    """Wait until every service runs in a container from this render; fail with their states otherwise. When an old
    container still stands STUCK_S in with no new one made for its service, on_stuck(the names) gets one go at it."""
    import time  # noqa: PLC0415 - patched in tests through the arguments

    sleep, clock = sleep or time.sleep, clock or time.time
    want, services = render.rendered_digest(text), compose_services(text)
    start = clock()
    deadline = start + timeout_s
    broken: list[tuple[str, str]] = []
    while True:
        rows = stack_containers(cfg, stack)
        ours = [r for r in rows if not LEFTOVER.match(r['name']) and (not want or r['rendered'] == want)]
        made = {r['service'] for r in ours}
        old = [
            r['name']
            for r in rows
            if not LEFTOVER.match(r['name']) and want and r['rendered'] != want and r['service'] not in made
        ]
        if on_stuck and old and clock() - start >= STUCK_S:
            warn(f'{stack}: {", ".join(old)} still stand{"s" if len(old) == 1 else ""} after the deploy; replacing it')
            on_stuck(old)
            on_stuck = None
            continue
        up = {r['service'] for r in ours if _up(r, kind)}
        if services and services <= up:
            leftovers = [r['name'] for r in rows if LEFTOVER.match(r['name'])]
            if leftovers:
                warn(
                    f'{stack}: containers left by an earlier, interrupted deploy: {", ".join(leftovers)} (docker rm them)'
                )
            return
        broken = [(r['name'], err) for r in ours if r['service'] not in up and (err := docker_error(r['name']))]
        if broken or clock() >= deadline:
            break
        sleep(5)
    errors = dict(broken)
    states = (
        ', '.join(
            f'{r["name"]} {r["state"]}' + (f' ({errors[r["name"]]})' if r['name'] in errors else '') for r in rows
        )
        or 'no containers'
    )
    why = 'failed to start' if errors else f'did not come up within {timeout_s // 60} min'
    raise Failed(f'{stack} {why}: {states}{coolify_status(cfg, stack)}')


def force_remove(name: str) -> None:
    """docker rm -f; when the runtime never reports the container's exit (a task stuck in the kernel, such as a crash
    dump that never finishes), its shim is killed first. The stuck task itself stays until the host reboots."""

    def remove() -> tuple[int, str]:
        try:
            return run(['docker', 'rm', '-f', name], check=False, timeout=120)
        except subprocess.TimeoutExpired:
            return 1, 'docker rm timed out'

    if remove()[0] == 0:
        return
    cid = run(['docker', 'inspect', '-f', '{{.Id}}', name], check=False)[1].strip()
    if not re.fullmatch(r'[0-9a-f]{64}', cid):
        return
    for pid in run(['pgrep', '-f', f'containerd-shim-runc-v2 .*-id {cid}'], check=False)[1].split():
        run(['kill', '-9', pid], check=False)
    rc, out = remove()
    if rc:
        raise Failed(f'{name} cannot be removed even with its shim gone ({out[-300:]}); the host needs a reboot')
    warn(
        f'{name} would not stop (a process stuck in the kernel), so its shim was killed to remove it; that process '
        'stays until the host reboots'
    )


def docker_error(name: str) -> str:
    rc, out = run(['docker', 'inspect', '-f', '{{.State.Error}}', name], check=False)
    return out.strip() if rc == 0 else ''


def _up(row: ContainerRow, kind: StackKind) -> bool:
    return row['state'] == 'running' or (kind == 'companion' and row['status'].startswith('Exited (0)'))


def compose_services(text: str) -> set[str]:
    """Service names of a rendered compose file (two-space keys under `services:`)."""
    body = text.split('\nservices:\n', 1)[-1] if '\nservices:\n' in text else ''
    names: set[str] = set()
    for line in body.splitlines():
        if line and not line.startswith(' '):
            break
        m = re.match(r'^  ([\w.-]+):\s*$', line)
        if m:
            names.add(m.group(1))
    return names


def stack_containers(cfg: Cluster, stack: str) -> list[ContainerRow]:
    fmt = '{{.Names}}\t{{.State}}\t{{.Status}}\t{{.Label "com.docker.compose.service"}}\t{{.Label "agentlab.rendered"}}'
    cmd = ['docker', 'ps', '-a', '--filter', f'label=com.docker.compose.project={project(cfg, stack)}', '--format', fmt]
    out = []
    for line in run(cmd, check=False)[1].splitlines():
        match line.split('\t'):
            case [name, state, status, service, digest]:
                out.append(ContainerRow(name=name, state=state, status=status, service=service, rendered=digest))
    return out


def coolify_status(cfg: Cluster, stack: str) -> str:
    """'; Coolify reports …' for a failure message, when Coolify deploys this stack and answers."""
    uuid = coolify.stack_uuid(stack_folder(cfg, stack)) if cfg['deploy'] == 'coolify' else None
    if not uuid:
        return ''
    try:
        status = coolify.Api(cfg).call('GET', f'/services/{uuid}').get('status', '')
    except (Failed, AttributeError):
        return ''
    return f'; Coolify reports the service as {status}' if status else ''


def connect(cfg: Cluster, plan: Plan) -> None:
    """Connect the edge, gate and hub to every agent network; recreates drop this, so it reruns every apply."""
    for service, alias in (('edge', None), ('gate', 'gate'), ('hub', 'hub')):
        for cid in containers(cfg, 'agentlab-core', service):
            joined = json.loads(run(['docker', 'inspect', '-f', '{{json .NetworkSettings.Networks}}', cid])[1] or '{}')
            for a in cfg['agents']:
                net = render.network(a['id'])
                if net not in joined:
                    cmd = ['docker', 'network', 'connect', *(['--alias', alias] if alias else []), net, cid]
                    plan.do(f'connect {service} to {net}', cmd)


def isolate(cfg: Cluster, plan: Plan, agents: Iterable[AgentCfg] | None = None) -> None:
    """Keep each agent container on its own network only (Coolify adds one; the firewall knows only agentlab-<id>)."""
    for a in cfg['agents'] if agents is None else agents:
        for cid in containers(cfg, f'agentlab-agent-{a["id"]}', 'agent'):
            joined = json.loads(run(['docker', 'inspect', '-f', '{{json .NetworkSettings.Networks}}', cid])[1] or '{}')
            for net in sorted(n for n in joined if n != render.network(a['id'])):
                plan.do(f'take agent {a["id"]} off {net}', ['docker', 'network', 'disconnect', net, cid])


def stop(cfg: Cluster, stack: str, plan: Plan) -> None:
    if cfg['deploy'] == 'coolify' and coolify.stack_uuid(stack_folder(cfg, stack)):
        uuid = coolify.stack_uuid(stack_folder(cfg, stack))
        plan.do(f'stop {stack}', fn=lambda: coolify.Api(cfg).call('POST', f'/services/{uuid}/stop'))
    else:
        plan.do(f'stop {stack}', ['docker', 'compose', '-p', stack, '-f', compose_file(cfg, stack), 'stop'])


def revive(cfg: Cluster, plan: Plan, only: Collection[str] | None = None) -> None:
    """Start agentlab's long-running containers that are stopped (a deploy only follows compose changes, so a container
    stopped by hand or by a disk shrink that couldn't restart it stayed down through every apply)."""
    for stack in render.stacks(cfg):
        if (only is not None and stack not in only) or deployed_this_run(stack):  # Coolify is starting those itself
            continue
        up = set(containers(cfg, stack))
        for cid in containers(cfg, stack, all_states=True):
            if cid in up:
                continue
            rc, info = run(
                ['docker', 'inspect', '-f', '{{.Name}} {{.HostConfig.RestartPolicy.Name}}', cid], check=False
            )
            name, _, policy = info.strip().lstrip('/').partition(' ')
            if rc == 0 and policy in ('always', 'unless-stopped'):  # not one-off containers meant to exit
                plan.do(f'start {name} (it was stopped)', ['docker', 'start', cid])


def start(cfg: Cluster, stack: str, plan: Plan) -> None:
    if cfg['deploy'] == 'coolify' and coolify.stack_uuid(stack_folder(cfg, stack)):
        uuid = coolify.stack_uuid(stack_folder(cfg, stack))
        plan.do(f'start {stack}', fn=lambda: coolify.Api(cfg).call('POST', f'/services/{uuid}/start'))
    else:
        plan.do(f'start {stack}', ['docker', 'compose', '-p', stack, '-f', compose_file(cfg, stack), 'up', '-d'])


def remove(cfg: Cluster, stack: str, plan: Plan) -> None:
    """Stop and delete a stack's containers (never its data)."""
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


def _rmtree(folder: str) -> None:
    for name in os.listdir(folder):
        os.remove(os.path.join(folder, name))
    os.rmdir(folder)


def remove_network(name: str, plan: Plan) -> None:
    if run(['docker', 'network', 'inspect', name], check=False)[0] == 0:
        plan.do(f'remove network {name}', fn=lambda: _disconnect_and_remove(name))


def _disconnect_and_remove(name: str, tries: int = 20, sleep: Callable[[float], None] = time.sleep) -> None:
    """Retried: Coolify deletes a stack in the background, so its containers can still be leaving."""
    for _ in range(tries):
        info = json.loads(run(['docker', 'network', 'inspect', name])[1])[0]
        for cid in info.get('Containers') or {}:
            run(['docker', 'network', 'disconnect', '-f', name, cid], check=False)
        rc, out = run(['docker', 'network', 'rm', name], check=False)
        if not rc:
            return
        sleep(3)
    raise Failed(f'could not remove network {name}: {out}')


def orphans(cfg: Cluster) -> list[str]:
    """Rendered stacks no longer in the config (an agent or companion removed by hand from cluster.toml)."""
    folder = rendered(cfg, 'compose')
    known = set(render.stacks(cfg))
    found = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
    out = [s for s in found if s not in known]
    for s in out:
        say(f'  {s} is no longer in cluster.toml: `agentctl agent remove` cleans it up, or remove it by hand')
    return out
