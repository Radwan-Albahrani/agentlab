"""`agentctl agent add | remove | list`. Add and remove edit cluster.toml as text (comments survive) and then apply,
so the edge, Cloudflare Access and the agent's stack all follow from the one file."""

import os

from . import apply, config, deploy, disks, render, tomledit
from .util import Needs, Plan, need_root, say, write_if_changed


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
    """The resolved config of edited text; raises with the problems before anything is written."""
    return config.loads(text)


def add(config_path, agent_id, owner, dry=False):
    with open(config_path) as f:
        text = f.read()
    new_text = tomledit.add_agent(text, agent_id, owner.lower())
    cfg = _checked(new_text)
    if dry:
        Plan(True).do(f'add agent {agent_id} ({owner}) to {config_path}')
        return apply.apply(cfg, config_path, dry=True)
    need_root('agentctl agent add')
    write_if_changed(config_path, new_text)
    say(f'added {agent_id} ({owner}) to {config_path}')
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
    if not keep_data:
        disks.remove_agent_files(a, plan)
    return {'plan': plan_text}
