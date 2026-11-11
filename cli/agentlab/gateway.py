"""Gateway rules (Zero Trust → Traffic policies) that fit agentlab into an account that already has its own setup.

Two promises, whatever the account's own rules say:
- agentlab's people reach agentlab's names: an Allow ahead of every other rule (Gateway stops at the first match).
- people who could enroll the Cloudflare One client only because of agentlab reach nothing else private: a Block
  for them on private address space, right after that Allow.
Everything else in the account (its rules, lists, enrollment policies) is read, never changed."""

import hashlib
import json

from . import config, render
from .util import Failed, Needs, warn

PRIVATE = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '100.64.0.0/10')
# where Gateway points a private hostname before the tunnel resolves it (the current and the legacy default range)
INITIAL = ('172.64.128.0/20', '100.80.0.0/16')
GROUP_DEPTH = 2


def _set(values):
    return '{' + ' '.join(json.dumps(v) for v in values) + '}'


def _ips(values):
    return '{' + ' '.join(values) + '}'  # IP ranges are bare in wirefilter


def _who(emails, domains):
    parts = [f'identity.email in {_set(sorted(emails))}'] if emails else []
    parts += [f'identity.email matches {json.dumps(".*@" + d.replace(".", "[.]") + "$")}' for d in sorted(domains)]
    return ' or '.join(parts)


class Enrollment:
    """Who could enroll the client before agentlab: the account's other enrollment policies, read rule by rule."""

    def __init__(self, api, account, ours):
        self.api, self.account, self.ours = api, account, ours
        self.unknown, self._lists, self._groups = set(), {}, {}

    def rules(self):
        apps = self.api.call('GET', f'/accounts/{self.account}/access/apps') or []
        app = next((a for a in apps if a.get('type') == 'warp'), None) or {}
        reusable = {p.get('id'): p for p in self.api.call('GET', f'/accounts/{self.account}/access/policies') or []}
        out = []
        for ref in app.get('policies') or []:
            p = reusable.get(ref.get('id')) or ref
            if str(p.get('name', '')).startswith(self.ours) or p.get('decision') not in ('allow', None):
                continue
            out.append((p.get('name') or p.get('id') or 'a policy', p.get('include') or []))
        return out

    def _list(self, list_id):
        if list_id not in self._lists:
            try:
                items = self.api.call('GET', f'/accounts/{self.account}/gateway/lists/{list_id}/items') or []
                self._lists[list_id] = {str(i.get('value', '')).lower() for i in items}
            except Failed:
                self._lists[list_id] = None
        return self._lists[list_id]

    def _group(self, group_id):
        if group_id not in self._groups:
            try:
                g = self.api.call('GET', f'/accounts/{self.account}/access/groups/{group_id}') or {}
                self._groups[group_id] = (g.get('name') or group_id, g.get('include') or [])
            except Failed:
                self._groups[group_id] = None
        return self._groups[group_id]

    def admits(self, email, rules, where, depth=0):
        """True when one include rule admits this email; rules agentctl can't read go into self.unknown."""
        domain = email.rsplit('@', 1)[-1]
        for r in rules:
            if 'everyone' in r:
                return True
            if (r.get('email') or {}).get('email', '').lower() == email:
                return True
            if (r.get('email_domain') or {}).get('domain', '').lower() == domain:
                return True
            if 'email_list' in r:
                listed = self._list((r['email_list'] or {}).get('id'))
                if listed is None:
                    self.unknown.add(f'{where} (an email list agentctl cannot read)')
                elif email in listed:
                    return True
                continue
            if 'group' in r and depth < GROUP_DEPTH:
                g = self._group((r['group'] or {}).get('id'))
                if g is None:
                    self.unknown.add(f'{where} (an Access group agentctl cannot read)')
                elif self.admits(email, g[1], f'{where} → group {g[0]}', depth + 1):
                    return True
                continue
            if not any(k in r for k in ('email', 'email_domain')):
                self.unknown.add(f'{where} ({", ".join(sorted(r))})')
        return False

    def newcomers(self, emails):
        """The emails no other enrollment policy admits: agentlab is why they can enroll."""
        rules = self.rules()
        return sorted(e for e in emails if not any(self.admits(e, inc, name) for name, inc in rules))


def wanted(cfg, newcomers):
    """[(suffix, filters, action, traffic, identity)] in the order they run. Gateway's network rules see the address
    a private hostname resolves to inside the tunnel (the edge's), so two rules cover it."""
    emails = {e.lower() for e in cfg_people(cfg)}
    domains = {d.lower() for d in cfg['auth']['allow_domains']}
    out = []
    if config.private_network(cfg):
        edge = f'net.dst.ip == {render.EDGE_IP} and net.dst.port in {{80 443}}'
        out.append(('allow', ['l4'], 'allow', edge, _who(emails, domains)))
    if newcomers:
        out.append(('only agentlab', ['l4'], 'block', f'net.dst.ip in {_ips(PRIVATE + INITIAL)}', _who(newcomers, ())))
    return out


def cfg_people(cfg):
    return render.people(cfg)


def _stamp(spec):
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]


def ensure(s, check_people=True):
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
    enrollment = Enrollment(s.api, s.account, s.name)
    emails = [e.lower() for e in cfg_people(s.cfg)]
    newcomers = enrollment.newcomers(emails) if check_people else []
    if enrollment.unknown:
        warn(
            'could not tell from ' + '; '.join(sorted(enrollment.unknown)) + ' who else may enroll the client, so '
            'agentlab treats its people as new to the account: they reach agentlab and nothing else private'
        )
    specs = wanted(s.cfg, newcomers)
    first = min((r.get('precedence') for r in theirs if isinstance(r.get('precedence'), int)), default=10_000)
    if first - len(specs) < 1 and specs:
        raise Failed(
            f"agentlab's {len(specs)} Gateway rules must come before your own, but your first one has precedence "
            f'{first}: move your rules down by {len(specs)} (Zero Trust → Traffic policies), then run setup again'
        )
    keep, bodies = set(), []
    for n, (suffix, filters, action, traffic, identity) in enumerate(specs):
        name = s.named(suffix)
        keep.add(name)
        spec = {'filters': filters, 'action': action, 'traffic': traffic, 'identity': identity}
        body = {
            'name': name,
            'description': f'made by agentlab ({_stamp(spec)}); agentctl cloudflare setup keeps it in step',
            'enabled': True,
            'precedence': first - len(specs) + n,
            **spec,
        }
        bodies.append((body, describe(suffix, newcomers)))
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
    return {'rules': len(theirs), 'newcomers': newcomers}


def _spec(body):
    return {k: body[k] for k in ('filters', 'action', 'traffic', 'identity')}


def describe(suffix, newcomers):
    if suffix == 'allow':
        return "agentlab's people reach agentlab, ahead of the account's own rules"
    return f'{len(newcomers)} people new to the account ({", ".join(newcomers)}) reach nothing else private'


def mine(s, rule):
    name = str(rule.get('name', ''))
    return name == s.name or name.startswith(s.name + ' ')


def drop(s):
    """No client in front any more: agentlab's Gateway rules go; nobody else's are touched."""
    path = f'/accounts/{s.account}/gateway/rules'
    try:
        rules = s.api.call('GET', path) or []
    except Failed:
        return
    for r in rules:
        if mine(s, r):
            s.write(f'remove the Gateway rule "{r["name"]}"', 'DELETE', f'{path}/{r["id"]}')
