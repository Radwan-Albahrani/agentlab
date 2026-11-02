"""Companions belong to their agent, which creates, changes and removes them (the watcher runs `agentctl companion
create | remove` when an agent drops a request file; an admin can run them too). The single source of truth is
<data>/state/companions.json; a [[companions]] entry in cluster.toml only seeds it on the first apply that sees it,
and its name is remembered so a companion its agent removed is not brought back. Only that companion's stack is
deployed or removed."""

import datetime
import json
import os
import shutil

from . import apply, config, deploy, render
from .util import Failed, Needs, Plan, need_root, say, write_if_changed


def save_state(data, state):
    path = config.state_file(data)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    write_if_changed(path, json.dumps(state, indent=1) + '\n', mode=0o600)


def _now():
    return datetime.datetime.now(datetime.UTC).isoformat(timespec='seconds')


def persist_seeds(cfg):
    """Record the cluster.toml companions this apply takes over (call only when really applying)."""
    if not cfg.get('seed'):
        return
    state = config.load_state(cfg['data'])
    for c in cfg['companions']:
        if c['name'] in cfg['seed']:
            state['companions'].append({**c, 'created_at': _now()})
    state['seeded'] = sorted(set(state['seeded']) | set(cfg['seed']))
    save_state(cfg['data'], state)


def create(config_path, agent_id, name, display_name='', kind='slack'):
    need_root('agentctl companion create')
    cfg = config.load(config_path)
    config.agent(cfg, agent_id)
    policy = cfg['companion_policy']
    if not policy['self_service']:
        raise Needs('agents may not create companions here ([companion_policy] self_service = false): ask an admin')
    if not config.AGENT_COMPANION.match(name) or name in config.RESERVED:
        raise Failed(f'{name!r}: a companion name is 2-30 lowercase letters, digits and dashes')
    if any(c['name'] == name for c in cfg['companions']):
        raise Failed(f'the name {name} is taken; pick another')
    if kind not in config.COMPANION_KINDS:
        raise Failed(f'kind must be one of {", ".join(sorted(config.COMPANION_KINDS))}')
    mine = [c for c in cfg['companions'] if c['agent'] == agent_id]
    if policy['max_per_agent'] and len(mine) >= policy['max_per_agent']:
        raise Failed(
            f'{agent_id} already has {len(mine)} companions (the limit is {policy["max_per_agent"]}); remove one first'
        )
    persist_seeds(cfg)
    state = config.load_state(cfg['data'])
    state['companions'].append(
        {
            'name': name,
            'display_name': (display_name or name)[:60],
            'kind': kind,
            'agent': agent_id,
            'created_at': _now(),
        }
    )
    save_state(cfg['data'], state)
    apply.apply(config.load(config_path), config_path, only={f'agentlab-companion-{name}'})
    say(f'companion {name} created for {agent_id}')
    return {'companion': name, 'agent': agent_id}


def remove(config_path, agent_id, name):
    """Stops and deletes one of the agent's companions; its data is archived, its code (the agent's checkout) stays."""
    need_root('agentctl companion remove')
    cfg = config.load(config_path)
    comp = next((c for c in cfg['companions'] if c['name'] == name), None)
    if not comp or comp['agent'] != agent_id:
        raise Failed(f'{agent_id} has no companion {name}')
    persist_seeds(cfg)
    plan = Plan(False)
    deploy.remove(cfg, f'agentlab-companion-{name}', plan)
    state = config.load_state(cfg['data'])
    state['companions'] = [e for e in state['companions'] if e.get('name') != name]
    save_state(cfg['data'], state)
    src = f'{cfg["data"]}/companions/{name}'
    if os.path.isdir(src):
        base = f'{cfg["data"]}/companions/.removed/{name}-{datetime.date.today().isoformat()}'
        dest, n = base, 1
        while os.path.exists(dest):
            n += 1
            dest = f'{base}-{n}'
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        plan.do(f'archive {src} to {dest}', fn=lambda: shutil.move(src, dest))
    apply.apply(config.load(config_path), config_path, only=set())
    say(f'companion {name} removed; its code stays in {render.companion_checkout(cfg, comp)}')
    return {'companion': name, 'agent': agent_id}


def owner_of(cfg, name):
    comp = next((c for c in cfg['companions'] if c['name'] == name), None)
    if not comp:
        raise Failed(f'no companion {name}')
    return comp['agent']
