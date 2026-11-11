import os

from . import apply, cloudflare, config, deploy, disks, render, tomledit
from .util import Failed, Needs, Plan, need_root, say, warn, write_if_changed


def listing(cfg):
    rows = [{k: a[k] for k in ('id', 'owner', 'memory', 'cpus', 'path')} for a in cfg['agents']]
    for r in rows:
        say(f'  {r["id"]:<16} {r["owner"]:<32} {r["memory"]:>5} RAM  {r["cpus"]} CPU  {r["path"]}')
    return rows


def adopt(cfg, agent_id):
    need_root('agentctl agent adopt')
    a = config.agent(cfg, agent_id)
    if apply.adopt(a, Plan(False)):
        return {'adopted': agent_id}
    say(f'  {agent_id}: nothing to do (already onboarded, or no Claude / Codex sign-in in {a["path"]}/home)')
    return {'adopted': None}


def _checked(text):
    return config.loads(text)


def limits(memory=None, cpus=None):
    """{key: value} for the agent block: memory as given ('12g'), cpus as a number; 'default' means None (drop it)."""
    out = {}
    if memory is not None:
        out['memory'] = None if memory == 'default' else memory.lower()
    if cpus is not None:
        out['cpus'] = None if cpus == 'default' else (float(cpus) if '.' in cpus else int(cpus))
    return out


def add(config_path, agent_id, owner, dry=False, memory=None, cpus=None):
    with open(config_path) as f:
        text = f.read()
    extra = {k: v for k, v in limits(memory, cpus).items() if v is not None}
    ports = next_ports(config.loads(text))
    new_text = tomledit.add_agent(text, agent_id, owner.lower(), extra, ports)
    if ports:
        say(f'{agent_id} is published like the others: ' + ', '.join(f'{t} {p}' for t, p in ports.items()))
    cfg = _checked(new_text)
    if dry:
        Plan(True).do(f'add agent {agent_id} ({owner}) to {config_path}')
        return apply.apply(cfg, config_path, dry=True)
    need_root('agentctl agent add')
    write_if_changed(config_path, new_text)
    say(f'added {agent_id} ({owner}) to {config_path}')
    out = apply.apply(cfg, config_path)
    cloudflare_names(config_path)
    return out


def cloudflare_names(config_path):
    """With Cloudflare set up, its names and routes follow the agents (pair hosts, the people allowed in)."""
    cfg = config.load(config_path)
    if not cloudflare.configured(cfg):
        return
    if cfg['auth']['ingress'] != 'cloudflared' and cfg['auth']['mode'] != 'cloudflare-access':
        return
    say('Cloudflare: updating names, routes and who may sign in')
    try:
        cloudflare.setup(cfg, Plan(False), config_path)
    except Failed as e:
        warn(f'the agents are up, but Cloudflare was not updated: {e} (agentctl cloudflare setup retries it)')


def next_ports(cfg):
    """When agents are published on host ports, the next free block laid out like the last agent's (7101-7105,
    7111-7115 -> 7121-7125); {} when none are."""
    shown = [a['publish'] for a in cfg['agents'] if a['publish']]
    if not shown:
        return {}
    agents = {p for pub in shown for p in pub.values()}
    used = agents | ({cfg['hub']['publish']} if cfg['hub']['publish'] else set())
    last = shown[-1]
    low = min(last.values())
    offsets = {tool: port - low for tool, port in sorted(last.items(), key=lambda i: i[1])}
    base = (max(agents) // 10 + 1) * 10 + low % 10
    while any(base + o in used or base + o > 65535 for o in offsets.values()):
        base += 10
    if base + max(offsets.values()) > 65535:
        raise Needs('no free host ports left to publish a new agent on: set [agents.publish] by hand')
    return {tool: base + o for tool, o in offsets.items()}


def set_limits(config_path, agent_id, memory=None, cpus=None, dry=False):
    """Change an agent's memory or CPUs; apply redeploys only that agent (once it is not mid-turn)."""
    with open(config_path) as f:
        text = f.read()
    config.agent(config.load(config_path), agent_id)
    changes = limits(memory, cpus)
    if not changes:
        raise Needs('nothing to change: give --memory and/or --cpus')
    new_text = text
    for key, value in changes.items():
        new_text = tomledit.set_agent_key(new_text, agent_id, key, value)
    cfg = _checked(new_text)
    a = config.agent(cfg, agent_id)
    say(f'{agent_id}: {a["memory"]} memory, {a["cpus"]} CPUs')
    if dry:
        return apply.apply(cfg, config_path, dry=True)
    need_root('agentctl agent set')
    write_if_changed(config_path, new_text)
    return apply.apply(cfg, config_path)


def remove(config_path, agent_id, keep_data=False, yes=False, dry=False):
    with open(config_path) as f:
        text = f.read()
    cfg = config.load(config_path)
    config.agent(cfg, agent_id)
    tied = [c['name'] for c in cfg['companions'] if c['agent'] == agent_id]
    if tied:
        raise Needs(f'{agent_id} has companions ({", ".join(tied)}): remove their [[companions]] blocks first')
    new_text = tomledit.remove_agent(text, agent_id)
    new_cfg = _checked(new_text)
    a = config.agent(cfg, agent_id)
    size = f'{disks.du(a["path"]) / 2**30:.1f} GiB' if os.path.isdir(a['path']) else 'missing'
    plan_text = [
        f'remove the [[agents]] block for {agent_id} from {config_path}',
        f'stop and delete the stack agentlab-agent-{agent_id} (its containers)',
        f'remove the network {render.network(agent_id)}',
        f'remove {agent_id} from the Cloudflare Access policy (if configured)',
        f'keep {a["path"]} ({size})'
        if keep_data
        else f'DELETE {a["path"]} ({size}): their home, workspace, T3 chats, all of it',
    ]
    for line in plan_text:
        say(f'  {line}')
    if dry:
        return {'plan': plan_text}
    if not keep_data and not yes:
        raise Needs(f"this deletes {agent_id}'s data for good: re-run with --yes, or with --keep-data to keep it")
    need_root('agentctl agent remove')
    plan = Plan(False)
    stack = f'agentlab-agent-{agent_id}'
    deploy.remove(cfg, stack, plan)
    deploy.remove_network(render.network(agent_id), plan)
    write_if_changed(config_path, new_text)
    apply.apply(new_cfg, config_path)
    cloudflare_names(config_path)
    if not keep_data:
        disks.remove_agent_files(a, plan)
    return {'plan': plan_text}
