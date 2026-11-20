"""Gateway rules (Zero Trust → Traffic policies) that fit agentlab into an account that already has its own setup.

One promise, whatever the account's own rules say: agentlab's people reach agentlab's names, an Allow ahead of every
other rule (Gateway stops at the first match). What else they reach is the account's own rules' call, as for anyone
else in it; agentlab never changes those rules, it only moves them down when there's no room ahead of them."""

import hashlib
import json
from collections.abc import Collection, Iterable
from typing import TYPE_CHECKING, NamedTuple, TypedDict

from . import config, render
from .config import Cluster
from .util import Failed, Json, Needs, warn

if TYPE_CHECKING:
    from .cloudflare import Setup  # cloudflare imports this module


class Wanted(NamedTuple):
    """One of agentlab's Gateway rules, as `wanted` lists them."""

    suffix: str
    filters: list[str]
    action: str
    traffic: str
    identity: str


class RuleSpec(TypedDict):
    """What a rule matches and does; its hash is stamped into the description."""

    filters: list[str]
    action: str
    traffic: str
    identity: str


class Rule(RuleSpec):
    name: str
    description: str
    enabled: bool
    precedence: int


class Seen(TypedDict):
    rules: int  # the account's own rules


def _set(values: Iterable[str]) -> str:
    return '{' + ' '.join(json.dumps(v) for v in values) + '}'


def _who(emails: Collection[str], domains: Collection[str]) -> str:
    parts = [f'identity.email in {_set(sorted(emails))}'] if emails else []
    parts += [f'identity.email matches {json.dumps(".*@" + d.replace(".", "[.]") + "$")}' for d in sorted(domains)]
    return ' or '.join(parts)


def wanted(cfg: Cluster) -> list[Wanted]:
    """[(suffix, filters, action, traffic, identity)] in the order they run. Gateway's network rules see the address
    a private hostname resolves to inside the tunnel (the edge's)."""
    emails = {e.lower() for e in cfg_people(cfg)}
    domains = {d.lower() for d in cfg['auth']['allow_domains']}
    out: list[Wanted] = []
    if config.private_network(cfg):
        edge = f'net.dst.ip == {render.EDGE_IP} and net.dst.port in {{80 443}}'
        out.append(Wanted('allow', ['l4'], 'allow', edge, _who(emails, domains)))
    return out


def cfg_people(cfg: Cluster) -> list[str]:
    return render.people(cfg)


def _stamp(spec: RuleSpec) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]


def ensure(s: 'Setup') -> Seen:
    """Make agentlab's rules match `wanted`, ahead of every other rule; `s` is a cloudflare.Setup."""
    from .cloudflare import PERMISSIONS, ApiError  # noqa: PLC0415 - cloudflare imports this module

    path = f'/accounts/{s.account}/gateway/rules'
    try:
        rules = s.api.call('GET', path) or []
    except ApiError as e:
        if e.status not in (401, 403):
            raise
        raise Needs(f'the token may not read Gateway rules: add "{PERMISSIONS["devices"]}"') from None
    ours = {r.get('name'): r for r in rules if mine(s, r)}
    theirs = [r for r in rules if r.get('name') not in ours]
    specs = wanted(s.cfg)
    slots, moves = places(theirs, len(specs))
    for r, to in moves:
        s.write(
            f'move your network rule "{r.get("name")}" from precedence {r["precedence"]} to {to}, so agentlab\'s rules '
            'can go first (its order among your rules and everything else about it stay the same)',
            'PUT',
            f'{path}/{r["id"]}',
            {**{k: r[k] for k in RULE_FIELDS if k in r and r[k] is not None}, 'precedence': to},
        )
    keep: set[str] = set()
    bodies: list[tuple[Rule, str]] = []
    for n, (suffix, filters, action, traffic, identity) in enumerate(specs):
        name = s.named(suffix)
        keep.add(name)
        spec: RuleSpec = {'filters': filters, 'action': action, 'traffic': traffic, 'identity': identity}
        body: Rule = {
            'name': name,
            'description': f'made by agentlab ({_stamp(spec)}); agentctl cloudflare setup keeps it in step',
            'enabled': True,
            'precedence': slots[n],
            **spec,
        }
        bodies.append((body, "agentlab's people reach agentlab, ahead of the account's own rules"))
    stale = [r for r in ours.values() if r.get('name') not in keep]
    # A precedence is held by one rule at a time: a rule that moves is removed first and added back in order;
    # one that only changes what it matches is updated in place, so it never lapses.
    moved = [b for b, _ in bodies if b['name'] in ours and ours[b['name']].get('precedence') != b['precedence']]
    for r in stale + [ours[b['name']] for b in moved]:
        s.write(f'remove the Gateway rule "{r["name"]}"', 'DELETE', f'{path}/{r["id"]}')
    for body, what in bodies:
        have = None if body in moved else ours.get(body['name'])
        try:
            if have is None:
                s.write(f'add the Gateway rule "{body["name"]}": {what}', 'POST', path, body)
            elif _stamp(_spec(body)) not in str(have.get('description', '')) or not have.get('enabled'):
                s.write(f'update the Gateway rule "{body["name"]}": {what}', 'PUT', f'{path}/{have["id"]}', body)
        except Failed as e:
            warn(f'Cloudflare refused the Gateway rule "{body["name"]}" ({e}); run setup again, or report it')
    return {'rules': len(theirs)}


# What a rule PUT carries; everything else Cloudflare returns (id, timestamps, version...) is its own bookkeeping.
RULE_FIELDS = (
    'name',
    'description',
    'action',
    'enabled',
    'filters',
    'traffic',
    'identity',
    'device_posture',
    'rule_settings',
    'schedule',
    'expiration',
    'precedence',
)


def places(theirs: list[Json], n: int) -> tuple[list[int], list[tuple[Json, int]]]:
    """(n precedences for agentlab's network rules, [(rule, new precedence)] for the account's network rules to move).
    Network and HTTP rules run in separate orders, so only the account's network rules matter for where agentlab's
    go: the n highest free numbers below its first one. Numbers are unique across all rules, so HTTP and DNS rules'
    numbers are only avoided. With no room there, agentlab's take the lowest free numbers and the account's network
    rules in the way move up past them, keeping their order (moves run last first, so none ever collide)."""
    if not n:
        return [], []
    held: dict[int, Json] = {r['precedence']: r for r in theirs if isinstance(r.get('precedence'), int)}
    network = sorted((r for r in held.values() if 'l4' in (r.get('filters') or [])), key=lambda r: r['precedence'])
    first = network[0]['precedence'] if network else max(held, default=0) + 1000
    below = [p for p in range(first - 1, -1, -1) if p not in held][:n]
    if len(below) == n:
        return sorted(below), []
    slots: list[int] = []
    p = 0
    while len(slots) < n:
        if p not in held:
            slots.append(p)
        p += 1
    moves: list[tuple[Json, int]] = []
    floor = slots[-1] + 1
    for r in network:
        if r['precedence'] >= floor:
            break
        to = floor
        while to in held and held[to] is not r and 'l4' not in (held[to].get('filters') or []):
            to += 1
        moves.append((r, to))
        floor = to + 1
    return slots, moves[::-1]


def _spec(body: Rule) -> RuleSpec:
    return {
        'filters': body['filters'],
        'action': body['action'],
        'traffic': body['traffic'],
        'identity': body['identity'],
    }


def mine(s: 'Setup', rule: Json) -> bool:
    name = str(rule.get('name', ''))
    return name == s.name or name.startswith(s.name + ' ')


def drop(s: 'Setup') -> None:
    """No client in front any more: agentlab's Gateway rules go; nobody else's are touched."""
    path = f'/accounts/{s.account}/gateway/rules'
    try:
        rules = s.api.call('GET', path) or []
    except Failed:
        return
    for r in rules:
        if mine(s, r):
            s.write(f'remove the Gateway rule "{r["name"]}"', 'DELETE', f'{path}/{r["id"]}')
