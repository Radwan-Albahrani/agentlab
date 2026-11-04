"""Stacks grouped by agent: its own stack (agentlab-agent-<id>) plus its companions' (agentlab-companion-<name>)."""

import cluster
import display
import store

AGENT_STACK, COMPANION_STACK = 'agentlab-agent-', 'agentlab-companion-'
STACK_LABELS = {'agentlab-core': 'Core · edge, gate, hub', 'coolify': 'Coolify', 'other': 'Other containers'}


def known(sid):
    """agentlab's own stacks and cluster.json's extra ones; anything else stays off the page."""
    return sid in STACK_LABELS or bool(domain_of(sid)[0]) or sid in cluster.extra_stacks()


def domain_of(sid):
    """(agent id, role): role is 'agent' for the agent's own stack, else the companion's name; (None, None) outside."""
    sid = sid or ''
    if sid.startswith(AGENT_STACK) and sid[len(AGENT_STACK) :] in cluster.agents():
        return sid[len(AGENT_STACK) :], 'agent'
    if sid.startswith(COMPANION_STACK):
        name = sid[len(COMPANION_STACK) :]
        owner = cluster.companions().get(name)
        if owner:
            return owner, name
    return None, None


def stack_label(sid):
    if sid in STACK_LABELS:
        return STACK_LABELS[sid]
    agent, role = domain_of(sid)
    if agent:
        return f'{agent} agent' if role == 'agent' else f'{cluster.display_name(role)} · {agent} companion'
    return sid


def healthy(r):
    return r['state'] == 'running' and 'unhealthy' not in (r.get('status') or '')


def by_stack():
    groups = {}
    for r in store.watch.containers().get('items') or []:
        sid = r.get('stack') or 'other'
        if known(sid):
            groups.setdefault(sid, []).append(r)
    return {k: sorted(v, key=lambda r: r['service']) for k, v in groups.items()}


def by_domain(stack_ids):
    """[(agent id or None, [stack ids])]: each visible agent's stacks, then the rest."""
    out = []
    for a in cluster.ids():
        mine = sorted((s for s in stack_ids if domain_of(s)[0] == a), key=lambda s: domain_of(s)[1] != 'agent')
        if mine and display.visible(f'profile.{a}'):
            out.append((a, mine))
    rest = sorted((s for s in stack_ids if not domain_of(s)[0]), key=_rest_order)
    return out + ([(None, rest)] if rest else [])


def _rest_order(sid):
    extra = cluster.extra_stacks()
    if sid in STACK_LABELS:
        return 0, list(STACK_LABELS).index(sid), sid
    return 1, extra.index(sid) if sid in extra else len(extra), sid


def container(r):
    return {
        'name': r['name'],
        'service': r['service'],
        'state': r['state'],
        'status': r.get('status') or r['state'],
        'image': r.get('image') or '',
        'healthy': healthy(r),
    }


def stack(sid, items):
    agent, role = domain_of(sid)
    return {
        'id': sid,
        'label': stack_label(sid),
        'profile': agent,
        'role': role,
        'containers': [container(r) for r in items],
    }
