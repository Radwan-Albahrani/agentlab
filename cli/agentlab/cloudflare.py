"""Cloudflare from the config. With cloudflared ingress: a remote-managed tunnel to the edge and a proxied CNAME per
hostname. With cloudflare-access sign-in also two Access applications: the people's (domain, hub, coolify) with a
policy listing exactly the agent owners and admins, and the apps' (pair hosts) with Bypass, because the T3 apps
can't do a browser sign-in and T3 accepts only paired sessions there. Every apply re-syncs the people policy, so
adding or removing an agent is also adding or removing their sign-in. Any Zero Trust login method works (the
one-time PIN by email needs no setup); `[auth.cloudflare] login_method` pins the people's app to one of them."""

import json
import os
import urllib.error
import urllib.request

from . import render, tomledit
from .util import Failed, Needs, say, write_if_changed

API = 'https://api.cloudflare.com/client/v4'
EDGE = 'http://127.0.0.1:8088'


class Api:
    def __init__(self, token, opener=None):
        self.token = token
        self.opener = opener or urllib.request.urlopen

    def call(self, method, path, body=None):
        req = urllib.request.Request(
            API + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'},
        )
        try:
            with self.opener(req, timeout=60) as r:
                reply = json.loads(r.read() or b'{}')
        except urllib.error.HTTPError as e:
            try:
                errors = json.loads(e.read()).get('errors')
            except ValueError:
                errors = e.reason
            raise Failed(f'Cloudflare {method} {path}: HTTP {e.code} {errors}') from None
        if not reply.get('success', True):
            raise Failed(f'Cloudflare {method} {path}: {reply.get("errors")}')
        return reply.get('result')


def hostnames(cfg):
    return render.public_hosts(cfg)


def signed_in_hosts(cfg):
    return [h for h in (cfg['domain'], cfg['hub_domain'], cfg['coolify_domain']) if h]


def pair_hosts(cfg):
    return [a['pair_host'] for a in cfg['agents'] if a['pair_host']]


def people(cfg):
    return render.people(cfg)


def configured(cfg):
    cf = cfg['cloudflare']
    return bool(cf['account_id'] and cf['zone'] and cf['api_token_file'] and os.path.isfile(cf['api_token_file']))


def api_for(cfg, opener=None):
    if not configured(cfg):
        raise Needs(
            'Cloudflare is not configured: set [cloudflare] account_id and zone in cluster.toml and save an API token '
            f'({"; ".join(PERMISSIONS.values())}) to '
            f'{cfg["cloudflare"]["api_token_file"] or "<data>/secrets/cloudflare-api.token"}'
        )
    with open(cfg['cloudflare']['api_token_file']) as f:
        return Api(f.read().strip(), opener)


class Setup:
    """Each step reads first and changes only what differs; on a dry run changes are printed, not made."""

    def __init__(self, cfg, api, plan):
        self.cfg, self.api, self.plan = cfg, api, plan
        self.account = cfg['cloudflare']['account_id']
        self.name = f'agentlab-{cfg["name"]}'

    def write(self, what, method, path, body=None):
        if self.plan.dry:
            self.plan.do(f'{what}: {method} {path}')
            return None
        result = self.api.call(method, path, body)
        self.plan.do(what)
        return result

    def tunnel(self):
        found = self.api.call('GET', f'/accounts/{self.account}/cfd_tunnel?name={self.name}&is_deleted=false') or []
        if found:
            return found[0]['id']
        made = self.write(
            f'create tunnel {self.name}',
            'POST',
            f'/accounts/{self.account}/cfd_tunnel',
            {'name': self.name, 'config_src': 'cloudflare'},
        )
        return made['id'] if made else '<new tunnel id>'

    def ingress(self, tunnel):
        want = [{'hostname': h, 'service': EDGE} for h in hostnames(self.cfg)] + [{'service': 'http_status:404'}]
        path = f'/accounts/{self.account}/cfd_tunnel/{tunnel}/configurations'
        current = None if tunnel.startswith('<') else self.api.call('GET', path)
        have = ((current or {}).get('config') or {}).get('ingress')
        if [{k: r.get(k) for k in ('hostname', 'service') if r.get(k)} for r in have or []] != want:
            self.write(
                'set the tunnel to send ' + ', '.join(hostnames(self.cfg)) + ' to the edge',
                'PUT',
                path,
                {'config': {'ingress': want}},
            )

    def token(self, tunnel):
        path = f'{self.cfg["data"]}/secrets/cloudflare-tunnel.token'
        if tunnel.startswith('<'):
            self.plan.do(f'save the tunnel token to {path}')
            return
        token = self.api.call('GET', f'/accounts/{self.account}/cfd_tunnel/{tunnel}/token')
        if self.plan.dry:
            if not os.path.isfile(path):
                self.plan.do(f'save the tunnel token to {path}')
            return
        if write_if_changed(path, token, mode=0o600):
            self.plan.do(f'saved the tunnel token to {path} (cloudflared reads it)')

    def dns(self, tunnel):
        zone_name = self.cfg['cloudflare']['zone']
        zones = self.api.call('GET', f'/zones?name={zone_name}') or []
        if not zones:
            raise Failed(f'zone {zone_name} not found for this API token')
        zone = zones[0]['id']
        target = f'{tunnel}.cfargotunnel.com'
        for host in hostnames(self.cfg):
            records = self.api.call('GET', f'/zones/{zone}/dns_records?name={host}') or []
            body = {'type': 'CNAME', 'name': host, 'content': target, 'proxied': True, 'comment': self.name}
            same = [r for r in records if r.get('type') == 'CNAME' and r.get('content') == target and r.get('proxied')]
            if same:
                continue
            if records:
                if len(records) > 1 or records[0].get('type') != 'CNAME':
                    raise Failed(f"{host} already has DNS records that are not this tunnel's CNAME; remove them first")
                self.write(f'point {host} at the tunnel', 'PUT', f'/zones/{zone}/dns_records/{records[0]["id"]}', body)
            else:
                self.write(f'add DNS {host} -> tunnel', 'POST', f'/zones/{zone}/dns_records', body)

    def policy(self, name, decision, include, describe):
        """A reusable Access policy, created or brought back to exactly `include`."""
        body = {'name': self.named(name), 'decision': decision, 'include': include}
        policies = self.api.call('GET', f'/accounts/{self.account}/access/policies') or []
        found = next((p for p in policies if p.get('name') == body['name']), None)
        if not found:
            made = self.write(
                f'create Access policy {describe}', 'POST', f'/accounts/{self.account}/access/policies', body
            )
            return made['id'] if made else f'<new {name} policy id>'
        if found.get('decision') != decision or _includes(found) != _includes(body):
            self.write(
                f'update Access policy {describe}',
                'PUT',
                f'/accounts/{self.account}/access/policies/{found["id"]}',
                body,
            )
        return found['id']

    def people_policy(self):
        include = [{'email': {'email': e}} for e in people(self.cfg)]
        domains = [{'email_domain': {'domain': d}} for d in self.cfg['auth']['allow_domains']]
        describe = f'to {len(include)} people' + (f' and {len(domains)} email domains' if domains else '')
        return self.policy('', 'allow', include + domains, describe)

    def app(self, name, hosts, policy, idps):
        body = {
            'name': self.named(name),
            'type': 'self_hosted',
            'domain': hosts[0],
            'destinations': [{'type': 'public', 'uri': h} for h in hosts],
            'session_duration': '24h',
            'app_launcher_visible': False,
            'policies': [{'id': policy, 'precedence': 1}],
            # Empty: every login method of the account is offered (and an earlier pin is cleared on update).
            'allowed_idps': idps,
            'auto_redirect_to_identity': len(idps) == 1,
        }
        apps = self.api.call('GET', f'/accounts/{self.account}/access/apps') or []
        found = next((a for a in apps if a.get('name') == body['name']), None)
        if not found:
            made = self.write(
                f'create Access application {name}: ' + ', '.join(hosts),
                'POST',
                f'/accounts/{self.account}/access/apps',
                body,
            )
            return (made or {}).get('aud', '')
        have_hosts = sorted(d.get('uri') for d in found.get('destinations') or [])
        have_policies = [p.get('id') for p in found.get('policies') or []]
        have_idps = sorted(found.get('allowed_idps') or [])
        if have_hosts != sorted(hosts) or have_policies != [policy] or have_idps != sorted(idps):
            self.write(
                f'update Access application {name}: ' + ', '.join(hosts),
                'PUT',
                f'/accounts/{self.account}/access/apps/{found["id"]}',
                body,
            )
        return found.get('aud', '')

    def named(self, name):
        """Everything agentlab makes is named agentlab-<cluster> (plus a suffix): it only ever touches those."""
        return f'{self.name} {name}' if name else self.name

    def access(self):
        providers = self.api.call('GET', f'/accounts/{self.account}/access/identity_providers') or []
        idps = login_methods(self.cfg, providers)
        aud = self.app('', signed_in_hosts(self.cfg), self.people_policy(), idps)
        if pair_hosts(self.cfg):
            bypass = self.policy('apps', 'bypass', [{'everyone': {}}], 'for the T3 apps (bypass)')
            self.app('apps', pair_hosts(self.cfg), bypass, [])
        return aud

    def audience(self, aud, config_path):
        if not aud or aud == self.cfg['auth']['cloudflare']['audience']:
            return
        if self.plan.dry:
            self.plan.do(f'write [auth.cloudflare] audience = {aud} into {config_path}')
            return
        with open(config_path) as f:
            text = f.read()
        write_if_changed(config_path, tomledit.set_key(text, 'auth.cloudflare', 'audience', aud))
        self.cfg['auth']['cloudflare']['audience'] = aud
        self.plan.do(f'wrote [auth.cloudflare] audience into {config_path} (the gate checks tokens against it)')


def _includes(policy):
    return sorted(json.dumps(r, sort_keys=True) for r in policy.get('include') or [])


def setup(cfg, plan, config_path, opener=None):
    if cfg['auth']['ingress'] != 'cloudflared' and cfg['auth']['mode'] != 'cloudflare-access':
        raise Failed(f'nothing to set up: auth.mode is {cfg["auth"]["mode"]} with {cfg["auth"]["ingress"]} ingress')
    s = Setup(cfg, api_for(cfg, opener), plan)
    if cfg['auth']['ingress'] == 'cloudflared':
        tunnel = s.tunnel()
        s.ingress(tunnel)
        s.token(tunnel)
        s.dns(tunnel)
    if cfg['auth']['mode'] == 'cloudflare-access':
        s.audience(s.access(), config_path)
    say(f'  Cloudflare: {", ".join(hostnames(cfg))} -> tunnel {s.name}; {len(people(cfg))} people may sign in')


def sync_people(cfg, plan, opener=None):
    """On apply: keep the Access policy equal to owners + admins, once `cloudflare setup` has created it."""
    if cfg['auth']['mode'] != 'cloudflare-access' or not configured(cfg):
        return
    s = Setup(cfg, api_for(cfg, opener), plan)
    policies = s.api.call('GET', f'/accounts/{s.account}/access/policies') or []
    if any(p.get('name') == s.named('') for p in policies):
        s.people_policy()


def login_methods(cfg, providers):
    """The identity provider ids people may use. With [auth.cloudflare] login_method set: exactly that one, so
    Access sends people straight there and doesn't offer the account's other methods (a one-time PIN meant for
    other apps, say). Otherwise none: Access offers every method the account has."""
    wanted = cfg['cloudflare'].get('login_method') or ''
    if wanted:
        match = [i['id'] for i in providers if str(i.get('name', '')).strip().lower() == wanted.strip().lower()]
        if not match:
            names = ', '.join(repr(i.get('name')) for i in providers) or 'none'
            raise Failed(f'[auth.cloudflare] login_method {wanted!r} is not a login method of this account ({names})')
        return match[:1]
    return []


# What each part of `cloudflare setup` needs, named as the token page in the dashboard shows it.
PERMISSIONS = {
    'tunnels': 'Account · Cloudflare One Connector: cloudflared → Edit (older accounts: Argo Tunnel (Legacy) → Edit; '
    'docs: Cloudflare Tunnel Write)',
    'access': 'Account · Access: Apps and Policies → Edit',
    'idps': 'Account · Access: Identity Providers → Read (older dashboards: Access: Organizations, Identity Providers, and Groups → Read)',
    'dns': 'Zone · DNS → Edit on the zone',
}


def verify_token(api, account):
    """True when Cloudflare accepts the token (user tokens and account-owned tokens verify at different paths)."""
    for path in ('/user/tokens/verify', f'/accounts/{account}/tokens/verify'):
        try:
            if (api.call('GET', path) or {}).get('status') == 'active':
                return True
        except Failed:
            continue
    return False


def probe_token(cfg, opener=None):
    """Read-only checks of what the token may do, for doctor: [(capability, ok)]. Each probe is a list call, so it
    proves the token reaches that area; it can't prove Edit without changing something."""
    api, account = api_for(cfg, opener), cfg['cloudflare']['account_id']
    if not verify_token(api, account):
        return None
    probes = []
    if cfg['auth']['ingress'] == 'cloudflared':
        probes.append(('tunnels', lambda: api.call('GET', f'/accounts/{account}/cfd_tunnel?per_page=1')))
        probes.append(('dns', lambda: _zone_records(api, cfg['cloudflare']['zone'])))
    if cfg['auth']['mode'] == 'cloudflare-access':
        probes.append(('access', lambda: api.call('GET', f'/accounts/{account}/access/apps')))
        probes.append(('idps', lambda: api.call('GET', f'/accounts/{account}/access/identity_providers')))
    out = []
    for name, probe in probes:
        try:
            probe()
            out.append((name, True))
        except Failed:
            out.append((name, False))
    return out


def _zone_records(api, zone_name):
    zones = api.call('GET', f'/zones?name={zone_name}') or []
    if not zones:
        raise Failed(f'zone {zone_name} not visible to the token')
    return api.call('GET', f'/zones/{zones[0]["id"]}/dns_records?per_page=1')


def identity_providers(cfg, opener=None):
    api = api_for(cfg, opener)
    return api.call('GET', f'/accounts/{cfg["cloudflare"]["account_id"]}/access/identity_providers') or []
