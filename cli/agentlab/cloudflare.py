"""Cloudflare from the config, in one of two networks.

private (the default): the names exist only for devices on the organization's Cloudflare One (WARP) client. Gateway
sends their traffic over the tunnel by private hostname routes; cloudflared resolves the names on this host and
connects to the edge on port 80. An Access application for those private hostnames lets in exactly the agent owners
and admins and, because it is plain HTTP inside the client's encrypted tunnel, issues the signed token the gate
verifies without Gateway TLS decryption. agentlab's own public DNS records and public apps are removed.

public: a public hostname per name (proxied CNAME to the tunnel) behind Access's sign-in page, plus a Bypass app for
the pair hosts (the T3 apps can't do a browser sign-in; T3 accepts only paired sessions there). require_warp adds a
Gateway device check to the people policy, so only devices on the client get past the sign-in.

Every apply re-syncs the people policy, so adding or removing an agent is also adding or removing their sign-in. Any Zero Trust login method works (the
one-time PIN by email needs no setup); `[auth.cloudflare] login_method` pins the people's app to one of them, and an
account with exactly one method gets that one. Only the API token is required: the account, the zone and the Zero
Trust team are read from the token and the domain, and written into cluster.toml the first time."""

import json
import os
import tomllib
import urllib.error
import urllib.request

from . import config, render, tomledit
from .util import Failed, Needs, Plan, say, write_if_changed

API = 'https://api.cloudflare.com/client/v4'


class ApiError(Failed):
    """A refused Cloudflare call; `status` is the HTTP status (0 when Cloudflare answered 200 with success: false)."""

    def __init__(self, message, status=0):
        super().__init__(message)
        self.status = status


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
            raise ApiError(f'Cloudflare {method} {path}: HTTP {e.code} {errors}', e.code) from None
        if not reply.get('success', True):
            raise ApiError(f'Cloudflare {method} {path}: {reply.get("errors")}')
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
    return os.path.isfile(cfg['cloudflare']['api_token_file'])


def api_for(cfg, opener=None):
    """The API with the saved token; the account, zone and team are filled in from it when the config leaves them
    out."""
    if not configured(cfg):
        raise Needs(
            'a Cloudflare API token is needed: create one (My Profile → API Tokens → Create Token → Custom) with '
            f'{"; ".join(PERMISSIONS[k] for k in needed_permissions(cfg))}, then save it with: '
            'agentctl secret set cloudflare-api'
        )
    with open(cfg['cloudflare']['api_token_file']) as f:
        api = Api(f.read().strip(), opener)
    discover(cfg, api)
    return api


def zone_of(api, host):
    """The zone serving `host`: the longest of its parent names this token can see."""
    labels = host.split('.')
    for i in range(len(labels) - 1):
        zones = api.call('GET', f'/zones?name={".".join(labels[i:])}') or []
        if zones:
            return zones[0]
    return None


def discover(cfg, api):
    """Fill in what the config leaves out, in memory: the zone and its account from the domain (else the token's
    only account), and the Zero Trust team from the account."""
    cf = cfg['cloudflare']
    if not cf['zone'] or not cf['account_id']:
        zone = zone_of(api, cfg['domain'])
        if zone:
            cf['zone'] = cf['zone'] or zone['name']
            cf['account_id'] = cf['account_id'] or (zone.get('account') or {}).get('id', '')
    if not cf['account_id']:
        accounts = api.call('GET', '/accounts') or []
        if len(accounts) != 1:
            raise Failed(
                f'{cfg["domain"]} is in no zone this token can see, and the token reaches {len(accounts)} accounts: '
                'give the token DNS access to the zone, or set [cloudflare] account_id'
            )
        cf['account_id'] = accounts[0]['id']
    if cfg['auth']['ingress'] == 'cloudflared' and not cf['zone']:
        raise Failed(f'no zone this token can see serves {cfg["domain"]}: give the token DNS access to it')
    if cfg['auth']['mode'] == 'cloudflare-access' and not cfg['auth']['cloudflare']['team']:
        try:
            org = api.call('GET', f'/accounts/{cf["account_id"]}/access/organizations') or {}
        except ApiError as e:
            if e.status not in (401, 403):
                raise
            raise Needs(
                'the token may not read the Zero Trust organization, which tells agentlab your team name: add '
                f'"{PERMISSIONS["org"]}" to the token in the dashboard (its value stays the same), or set '
                '[auth.cloudflare] team = "<the part before .cloudflareaccess.com>" in cluster.toml'
            ) from None
        team = str(org.get('auth_domain', '')).removesuffix('.cloudflareaccess.com')
        if not team:
            raise Failed(
                'this account has no Zero Trust organization yet: open one.dash.cloudflare.com once to make it'
            )
        cfg['auth']['cloudflare']['team'] = team


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

    def policy(self, name, decision, include, describe, require=()):
        """A reusable Access policy, created or brought back to exactly `include` (and `require`)."""
        body = {'name': self.named(name), 'decision': decision, 'include': include, 'require': list(require)}
        policies = self.api.call('GET', f'/accounts/{self.account}/access/policies') or []
        found = next((p for p in policies if p.get('name') == body['name']), None)
        if not found:
            made = self.write(
                f'create Access policy {describe}', 'POST', f'/accounts/{self.account}/access/policies', body
            )
            return made['id'] if made else f'<new {name} policy id>'
        if found.get('decision') != decision or _rules(found) != _rules(body):
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
        require = []
        if self.cfg['auth']['cloudflare']['require_warp']:
            require = [{'device_posture': {'integration_uid': self.gateway_check()}}]
            describe += ' on the Cloudflare One client'
        return self.policy('', 'allow', include + domains, describe, require)

    def gateway_check(self):
        """The account's Gateway device posture check (traffic filtered by this organization's Gateway): Access
        policies require it by id. Made when missing; it changes nothing for other apps until a policy uses it."""
        try:
            checks = self.api.call('GET', f'/accounts/{self.account}/devices/posture') or []
        except ApiError as e:
            if e.status not in (401, 403):
                raise
            raise Needs(f'the token may not read device posture checks: add "{PERMISSIONS["devices"]}"') from None
        found = next((c for c in checks if c.get('type') == 'gateway'), None)
        if found:
            return found['id']
        made = self.write(
            'create the Gateway device posture check',
            'POST',
            f'/accounts/{self.account}/devices/posture',
            {'name': 'Gateway', 'type': 'gateway', 'description': f'made by {self.name}'},
        )
        return (made or {}).get('id', '<new gateway check id>')

    def app(self, name, hosts, policy, idps, private=False):
        destinations = (
            [{'type': 'private', 'hostname': h, 'port_range': '80'} for h in hosts]
            if private
            else [{'type': 'public', 'uri': h} for h in hosts]
        )
        warp = private or self.cfg['auth']['cloudflare']['require_warp']
        body = {
            'name': self.named(name),
            'type': 'self_hosted',
            'domain': hosts[0],
            'destinations': destinations,
            'session_duration': '24h',
            'app_launcher_visible': False,
            'policies': [{'id': policy, 'precedence': 1}],
            # Empty: every login method of the account is offered (and an earlier pin is cleared on update).
            'allowed_idps': idps,
            'auto_redirect_to_identity': len(idps) == 1,
            # Devices on the client sign in with their client session, so the T3 desktop and phone apps work too
            'allow_authenticate_via_warp': True if warp else None,
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
        have_policies = [p.get('id') for p in found.get('policies') or []]
        have_idps = sorted(found.get('allowed_idps') or [])
        if (
            _destinations(found) != _destinations(body)
            or have_policies != [policy]
            or have_idps != sorted(idps)
            or bool(found.get('allow_authenticate_via_warp')) != bool(warp)
        ):
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
        private = config.private_network(self.cfg)
        aud = self.app('', signed_in_hosts(self.cfg), self.people_policy(), idps, private=private)
        if pair_hosts(self.cfg):
            bypass = self.policy('apps', 'bypass', [{'everyone': {}}], 'for the T3 apps (bypass)')
            self.app('apps', pair_hosts(self.cfg), bypass, [])
        elif private or self.cfg['auth']['cloudflare']['require_warp']:
            self.drop_apps_bypass()  # a Bypass app left from a public setup would be a way around the client
        return aud

    def drop_apps_bypass(self):
        apps = self.api.call('GET', f'/accounts/{self.account}/access/apps') or []
        for app in (a for a in apps if a.get('name') == self.named('apps')):
            path = f'/accounts/{self.account}/access/apps/{app["id"]}'
            self.write(f'remove Access application {app["name"]} (bypass)', 'DELETE', path)
        policies = self.api.call('GET', f'/accounts/{self.account}/access/policies') or []
        for p in (p for p in policies if p.get('name') == self.named('apps')):
            self.write(
                f'remove Access policy {p["name"]}', 'DELETE', f'/accounts/{self.account}/access/policies/{p["id"]}'
            )

    # ---------------------------------------------------------------- private network
    def private_ingress(self, tunnel):
        """No public hostnames on the tunnel; Gateway sends the client's traffic by the hostname routes below."""
        want = {'ingress': [{'service': 'http_status:404'}], 'warp-routing': {'enabled': True}}
        path = f'/accounts/{self.account}/cfd_tunnel/{tunnel}/configurations'
        current = None if tunnel.startswith('<') else self.api.call('GET', path)
        have = (current or {}).get('config') or {}
        ingress = [{k: r.get(k) for k in ('hostname', 'service') if r.get(k)} for r in have.get('ingress') or []]
        if ingress != want['ingress'] or not (have.get('warp-routing') or {}).get('enabled'):
            self.write('set the tunnel to private routing only (no public hostnames)', 'PUT', path, {'config': want})

    def hostname_routes(self, tunnel):
        """A private hostname route per name to this tunnel; agentlab's own routes (by comment) for names it no
        longer serves go. Someone else's route for one of the names stops setup instead of being taken over."""
        path = f'/accounts/{self.account}/zerotrust/routes/hostname'
        try:
            routes = self.api.call('GET', path) or []
        except ApiError as e:
            if e.status not in (401, 403):
                raise
            raise Needs(f'the token may not manage tunnel hostname routes: add "{PERMISSIONS["routes"]}"') from None
        hosts = signed_in_hosts(self.cfg)
        for host in hosts:
            same = [r for r in routes if r.get('hostname') == host]
            if any(r.get('tunnel_id') == tunnel for r in same):
                continue
            if any(r.get('comment') != self.name for r in same):
                raise Failed(f"{host} already has a hostname route to another tunnel (not agentlab's): remove it first")
            for r in same:
                self.write(f'remove the old route for {host}', 'DELETE', f'{path}/{r["id"]}')
            body = {'hostname': host, 'tunnel_id': tunnel, 'comment': self.name}
            self.write(f'route {host} over the tunnel (private hostname)', 'POST', path, body)
        for r in routes:
            if r.get('comment') == self.name and r.get('hostname') not in hosts:
                self.write(f'remove the route for {r["hostname"]}', 'DELETE', f'{path}/{r["id"]}')

    def drop_public_dns(self, tunnel):
        """Private names must not resolve publicly: remove the DNS records agentlab made (its comment, pointing at its
        tunnel). Records anyone else made stay."""
        zone_name = self.cfg['cloudflare']['zone']
        zones = (self.api.call('GET', f'/zones?name={zone_name}') or []) if zone_name else []
        if not zones:
            return
        zone = zones[0]['id']
        target = f'{tunnel}.cfargotunnel.com'
        for r in self.api.call('GET', f'/zones/{zone}/dns_records?per_page=500') or []:
            if r.get('comment') == self.name and r.get('content') == target:
                path = f'/zones/{zone}/dns_records/{r["id"]}'
                self.write(f'remove the public DNS record {r["name"]}', 'DELETE', path)

    def remember(self, config_path, values):
        """Write what setup found or made into cluster.toml: the gate reads the team and audience from there, and
        later commands skip the lookups."""
        with open(config_path) as f:
            text = f.read()
        current, new = tomllib.loads(text), text
        for (section, key), value in values.items():
            head, _, sub = section.partition('.')
            table = (current.get(head) or {}).get(sub) or {} if sub else current.get(head) or {}
            if not value or table.get(key) == value:
                continue
            if self.plan.dry:
                self.plan.do(f'write [{section}] {key} = {value} into {config_path}')
                continue
            new = tomledit.set_key(new, section, key, value)
            self.plan.do(f'wrote [{section}] {key} into {config_path}')
        if new != text:
            write_if_changed(config_path, new)


def _rules(policy):
    return [sorted(json.dumps(r, sort_keys=True) for r in policy.get(k) or []) for k in ('include', 'require')]


def _destinations(app):
    kept = ({k: v for k, v in d.items() if v not in (None, '')} for d in app.get('destinations') or [])
    return sorted(json.dumps(d, sort_keys=True) for d in kept)


def setup(cfg, plan, config_path, opener=None):
    if cfg['auth']['ingress'] != 'cloudflared' and cfg['auth']['mode'] != 'cloudflare-access':
        raise Failed(f'nothing to set up: auth.mode is {cfg["auth"]["mode"]} with {cfg["auth"]["ingress"]} ingress')
    s = Setup(cfg, api_for(cfg, opener), plan)
    if cfg['auth']['ingress'] == 'cloudflared':
        tunnel = s.tunnel()
        if config.private_network(cfg):
            s.private_ingress(tunnel)
            s.hostname_routes(tunnel)
            s.drop_public_dns(tunnel)
        else:
            s.ingress(tunnel)
            s.dns(tunnel)
        s.token(tunnel)
    cf = cfg['cloudflare']
    found = {('cloudflare', 'account_id'): cf['account_id'], ('cloudflare', 'zone'): cf['zone']}
    if cfg['auth']['mode'] == 'cloudflare-access':
        access = cfg['auth']['cloudflare']
        access['audience'] = s.access() or access['audience']
        found[('auth.cloudflare', 'team')] = access['team']
        found[('auth.cloudflare', 'audience')] = access['audience']
    s.remember(config_path, found)
    private = config.private_network(cfg)
    where = 'private: Cloudflare One client only' if private else 'public sign-in page'
    names = signed_in_hosts(cfg) if private else hostnames(cfg)
    say(f'  Cloudflare: {", ".join(names)} -> tunnel {s.name} ({where}); {len(people(cfg))} people may sign in')


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
    other apps, say). With a single method in the account: that one, for the same straight-through sign-in.
    Otherwise none: Access offers every method the account has."""
    wanted = cfg['cloudflare'].get('login_method') or ''
    if wanted:
        match = [i['id'] for i in providers if str(i.get('name', '')).strip().lower() == wanted.strip().lower()]
        if not match:
            names = ', '.join(repr(i.get('name')) for i in providers) or 'none'
            raise Failed(f'[auth.cloudflare] login_method {wanted!r} is not a login method of this account ({names})')
        return match[:1]
    return [providers[0]['id']] if len(providers) == 1 and providers[0].get('id') else []


# What each part of `cloudflare setup` needs, named as the token page in the dashboard shows it.
PERMISSIONS = {
    'tunnels': 'Account · Cloudflare One Connector: cloudflared → Edit',
    'access': 'Account · Access: Apps and Policies → Edit (newer dashboards: Access: Apps → Edit, Access: Policies → Edit)',
    'idps': 'Account · Access: Identity Providers → Read',
    'org': 'Account · Access: Organizations → Read',
    'dns': 'Zone · DNS → Edit on the zone',
    # network = "private" (and require_warp): tunnel hostname routes, and the client settings doctor checks
    'routes': 'Account · Cloudflare One Networks → Edit (older dashboards: Cloudflare Tunnel → Edit)',
    'devices': 'Account · Zero Trust → Read (→ Edit also lets agentlab create the Gateway posture check)',
}


def needed_permissions(cfg):
    """What this config needs from the token, as PERMISSIONS keys."""
    keys = ['tunnels', 'dns', 'access', 'idps', 'org']
    if config.private_network(cfg):
        keys += ['routes', 'devices']
    elif cfg['auth']['cloudflare']['require_warp']:
        keys.append('devices')
    return keys


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
        if not cfg['auth']['cloudflare']['team']:  # only needed to find the team name
            probes.append(('org', lambda: api.call('GET', f'/accounts/{account}/access/organizations')))
        if config.private_network(cfg):
            probes.append(('routes', lambda: api.call('GET', f'/accounts/{account}/zerotrust/routes/hostname')))
        if config.private_network(cfg) or cfg['auth']['cloudflare']['require_warp']:
            probes.append(('devices', lambda: api.call('GET', f'/accounts/{account}/devices/settings')))
    out = []
    for name, probe in probes:
        try:
            probe()
            out.append((name, True))
        except Failed:
            out.append((name, False))
    return out


def client_only_checks(cfg, opener=None):
    """Read-only facts doctor shows for network = "private" or require_warp: [(id, ok, message, fix, severity)].
    Each is what `cloudflare setup` made or what the organization must have on for it to work."""
    api, account = api_for(cfg, opener), cfg['cloudflare']['account_id']
    s = Setup(cfg, api, Plan(True))
    out, private = [], config.private_network(cfg)
    try:
        settings = api.call('GET', f'/accounts/{account}/devices/settings') or {}
        out.append(
            (
                'gateway-proxy',
                bool(settings.get('gateway_proxy_enabled')),
                'Gateway proxy is on (the client sends web traffic through Gateway)',
                'Zero Trust → Settings → Network → Firewall: turn on Proxy (TCP); private hostnames need it',
                'error' if private else 'warning',
            )
        )
    except Failed:
        out.append(
            (
                'gateway-proxy',
                True,
                "couldn't read the client settings with this token: check Zero Trust → Settings → Network → Proxy is on",
                '',
                'info',
            )
        )
    apps = api.call('GET', f'/accounts/{account}/access/apps') or []
    app = next((a for a in apps if a.get('name') == s.name), None)
    out.append(
        (
            'client-sign-in',
            bool(app and app.get('allow_authenticate_via_warp')),
            'devices on the client are signed in with their client session (no browser login; the T3 apps work)',
            'agentctl cloudflare setup; also check Zero Trust → Settings → WARP Client → Device enrollment: '
            '"WARP authentication identity" on',
            'error',
        )
    )
    if private:
        hosts = signed_in_hosts(cfg)
        kinds = {d.get('type') for d in (app or {}).get('destinations') or []}
        out.append(
            (
                'private-app',
                kinds == {'private'},
                'the Access application covers the private hostnames only',
                'agentctl cloudflare setup',
                'error',
            )
        )
        try:
            routes = api.call('GET', f'/accounts/{account}/zerotrust/routes/hostname') or []
        except Failed:
            routes = None
        if routes is None:
            out.append(
                ('hostname-routes', False, 'tunnel hostname routes readable', f'add "{PERMISSIONS["routes"]}"', 'error')
            )
        else:
            missing = [h for h in hosts if not any(r.get('hostname') == h for r in routes)]
            out.append(
                (
                    'hostname-routes',
                    not missing,
                    'every name is routed over the tunnel'
                    if not missing
                    else f'no hostname route for {", ".join(missing)}',
                    'agentctl cloudflare setup',
                    'error',
                )
            )
        public = []
        zone = cfg['cloudflare']['zone']
        zones = (api.call('GET', f'/zones?name={zone}') or []) if zone else []
        for host in hosts if zones else []:
            if api.call('GET', f'/zones/{zones[0]["id"]}/dns_records?name={host}'):
                public.append(host)
        out.append(
            (
                'no-public-dns',
                not public,
                'no public DNS records for the private names'
                if not public
                else f'public DNS records exist for {", ".join(public)} (the names resolve outside the client)',
                "agentctl cloudflare setup removes agentlab's own; remove any others in DNS → Records",
                'warning',
            )
        )
    if cfg['auth']['cloudflare']['require_warp']:
        policies = api.call('GET', f'/accounts/{account}/access/policies') or []
        people = next((p for p in policies if p.get('name') == s.name), {})
        posture = any('device_posture' in r for r in people.get('require') or [])
        out.append(
            (
                'require-client',
                posture,
                'the sign-in policy requires the Cloudflare One client (Gateway device check)',
                'agentctl cloudflare setup',
                'error',
            )
        )
    return out


def _zone_records(api, zone_name):
    zones = api.call('GET', f'/zones?name={zone_name}') or []
    if not zones:
        raise Failed(f'zone {zone_name} not visible to the token')
    return api.call('GET', f'/zones/{zones[0]["id"]}/dns_records?per_page=1')


def identity_providers(cfg, opener=None):
    api = api_for(cfg, opener)
    return api.call('GET', f'/accounts/{cfg["cloudflare"]["account_id"]}/access/identity_providers') or []
