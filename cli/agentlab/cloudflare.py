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

import ipaddress
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
        try:
            result = self.api.call(method, path, body)
        except ApiError as e:
            raise refused(e, what) or e from None
        self.plan.do(what)
        return result

    def find_tunnel(self):
        found = self.api.call('GET', f'/accounts/{self.account}/cfd_tunnel?name={self.name}&is_deleted=false') or []
        return found[0]['id'] if found else ''

    def tunnel(self):
        found = self.find_tunnel()
        if found:
            return found
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
        """The people's application (and, public only, the pair hosts' Bypass app). Removing a Bypass app left from
        a public setup is left to `cleanup`, after the new way in works."""
        providers = self.api.call('GET', f'/accounts/{self.account}/access/identity_providers') or []
        idps = login_methods(self.cfg, providers)
        private = config.private_network(self.cfg)
        aud = self.app('', signed_in_hosts(self.cfg), self.people_policy(), idps, private=private)
        if pair_hosts(self.cfg):
            bypass = self.policy('apps', 'bypass', [{'everyone': {}}], 'for the T3 apps (bypass)')
            self.app('apps', pair_hosts(self.cfg), bypass, [])
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

    def drop_hostname_routes(self):
        """Back to public: agentlab's own private hostname routes (by comment) go; anyone else's stay."""
        path = f'/accounts/{self.account}/zerotrust/routes/hostname'
        try:
            routes = self.api.call('GET', path) or []
        except ApiError as e:
            if e.status not in (401, 403):
                raise
            return  # never had them: the token can't even list routes
        for r in routes:
            if r.get('comment') == self.name:
                self.write(f'remove the private route for {r["hostname"]}', 'DELETE', f'{path}/{r["id"]}')

    def current_ingress(self, tunnel):
        """'private' (404-only, warp-routing on), 'public' (hostnames on the tunnel), or '' (no tunnel/config yet)."""
        if tunnel.startswith('<'):
            return ''
        try:
            conf = (self.api.call('GET', f'/accounts/{self.account}/cfd_tunnel/{tunnel}/configurations') or {}).get(
                'config'
            ) or {}
        except ApiError:
            return ''
        if any(r.get('hostname') for r in conf.get('ingress') or []):
            return 'public'
        return 'private' if (conf.get('warp-routing') or {}).get('enabled') else ''

    def preflight(self):
        """Everything this run will need, checked read-only before it changes anything (dry runs too): a gap is
        exit 2 with the exact fix, never a half-switched tunnel. Reads stand in for edits (they can't be proved
        without editing) unless the token may read its own permissions; the change steps are ordered so that a
        refused edit still leaves the old way in working."""
        gaps, cfg, account = [], self.cfg, self.account
        private = config.private_network(cfg)
        warp = private or cfg['auth']['cloudflare']['require_warp']
        reads = []
        if cfg['auth']['ingress'] == 'cloudflared':
            reads += [('tunnels', f'/accounts/{account}/cfd_tunnel?per_page=1')]
            if cfg['cloudflare']['zone']:
                reads += [('dns', f'/zones?name={cfg["cloudflare"]["zone"]}')]
        if cfg['auth']['mode'] == 'cloudflare-access':
            reads += [
                ('access', f'/accounts/{account}/access/apps'),
                ('access', f'/accounts/{account}/access/policies'),
                ('idps', f'/accounts/{account}/access/identity_providers'),
            ]
        if private:
            reads += [('routes', f'/accounts/{account}/zerotrust/routes/hostname')]
        if warp:
            reads += [('devices', f'/accounts/{account}/devices/settings')]
        answers = {}
        for key, path in reads:
            try:
                answers[path] = self.api.call('GET', path)
            except ApiError as e:
                if e.status not in (401, 403):
                    raise
                gaps.append(f'add "{PERMISSIONS[key]}" to the token')
        for key in missing_edit_permissions(self.api, account, needed_permissions(cfg)):
            gaps.append(f'add "{PERMISSIONS[key]}" to the token (it can read but not change this)')
        if warp:
            try:
                self.api.call('GET', f'/accounts/{account}/access/organizations')
            except ApiError as e:
                if e.status not in (401, 403):
                    raise
                gaps.append(f'add "{PERMISSIONS["org"]}" to the token (for the client session setting)')
        return list(dict.fromkeys(gaps))

    # ---------------------------------------------------------------- account settings agentlab turns on itself
    def prerequisites(self):
        """What the organization needs before clients can use agentlab, turned on through the token only when it is
        off or unset: the client session duration (never shortened or changed once set, and never "client
        authentication for all applications") and, for private, Gateway's TCP and UDP proxy (never turned off)."""
        private = config.private_network(self.cfg)
        if not (private or self.cfg['auth']['cloudflare']['require_warp']):
            return
        path = f'/accounts/{self.account}/access/organizations'
        org = self.api.call('GET', path) or {}
        if not org.get('warp_auth_session_duration'):
            duration = self.cfg['cloudflare'].get('client_session') or '24h'
            body = {k: v for k, v in org.items() if k not in ORG_READ_ONLY}
            body['warp_auth_session_duration'] = duration
            self.write(
                f'set the Cloudflare One Client authentication session duration to {duration} (it had none)',
                'PUT',
                path,
                body,
            )
        if private:
            path = f'/accounts/{self.account}/devices/settings'
            settings = self.api.call('GET', path) or {}
            off = [k for k in ('gateway_proxy_enabled', 'gateway_udp_proxy_enabled') if not settings.get(k)]
            if off:
                names = ' and '.join('TCP' if k == 'gateway_proxy_enabled' else 'UDP' for k in off)
                self.write(
                    f'turn on the Gateway proxy for {names} (it was off)', 'PATCH', path, dict.fromkeys(off, True)
                )

    def enrollment(self, policy):
        """Everyone agentlab's policy admits may enroll the Cloudflare One client: its policy is appended to the
        account's device enrollment application, after every policy already there (kept, in their order)."""
        apps = self.api.call('GET', f'/accounts/{self.account}/access/apps') or []
        app = next((a for a in apps if a.get('type') == 'warp'), None)
        if app is None:
            raise Needs(
                'this account has no device enrollment settings yet: open Zero Trust → Team & Resources → Devices '
                'once (it creates them), then run agentctl setup again'
            )
        have = app.get('policies') or []
        if any(p.get('id') == policy for p in have):
            return
        top = max((p.get('precedence') or i + 1 for i, p in enumerate(have)), default=0)
        body = {k: v for k, v in app.items() if k not in APP_READ_ONLY}
        body['policies'] = [*have, {'id': policy, 'precedence': top + 1}]
        self.write(
            f'let {self.named("")} enroll the Cloudflare One client (added after the {len(have)} existing enrollment '
            'policies)',
            'PUT',
            f'/accounts/{self.account}/access/apps/{app["id"]}',
            body,
        )


ORG_READ_ONLY = ('created_at', 'updated_at')
APP_READ_ONLY = ('id', 'uid', 'aud', 'created_at', 'updated_at')


GATEWAY_PROXY_FIX = (
    'agentctl cloudflare setup turns the Gateway proxy on (with "Account · Zero Trust → Edit"); or turn on "Allow '
    'Secure Web Gateway to proxy traffic" yourself under Zero Trust → Traffic policies → Traffic settings'
)
CLIENT_SESSION_FIX = (
    'the account needs a Cloudflare One Client authentication session duration: agentlab sets it when the token has '
    '"Account · Access: Organizations → Edit"; or set it yourself under Zero Trust → Access → Settings (newer '
    'dashboards: Access controls → Access settings), e.g. 24h'
)


def refused(e, what):
    """A change Cloudflare refused that a person must fix, as Needs with the fix; None for anything else."""
    text = str(e)
    if '12130' in text or 'allow_authenticate_via_warp cannot be set' in text:
        return Needs(f'Cloudflare refused to {what}: {CLIENT_SESSION_FIX}. Then run agentctl setup again.')
    if e.status in (401, 403):
        key = permission_for(text)
        add = f'add "{PERMISSIONS[key]}" to the token' if key else 'give the token the permission for it'
        return Needs(
            f'Cloudflare refused to {what} (HTTP {e.status}): {add} in the dashboard (its value stays the same), '
            'then run agentctl setup again'
        )
    return None


def permission_for(text):
    """Which PERMISSIONS entry a refused call's path belongs to."""
    for fragment, key in (
        ('/zerotrust/routes', 'routes'),
        ('/cfd_tunnel', 'tunnels'),
        ('/dns_records', 'dns'),
        ('/access/organizations', 'org'),
        ('/identity_providers', 'idps'),
        ('/access/', 'access'),
        ('/devices/', 'devices'),
    ):
        if fragment in text:
            return key
    return ''


# The token's own permission groups, when it may read them, prove the edits read probes can't: name fragments that
# mean "may change" each area (generous on purpose: an unrecognised name never blocks, only a missing area does).
EDIT_GROUPS = {
    'tunnels': ('tunnel', 'connector', 'cloudflared'),
    'dns': ('dns',),
    'access': ('access: apps', 'access: policies', 'access: apps and policies'),
    'routes': ('cloudflare one networks', 'networks', 'tunnel', 'zero trust'),
}


def own_permission_groups(api, account):
    """The names of the token's permission groups, or None when the token may not read itself (the usual case)."""
    for verify, read in (('/user/tokens/verify', '/user/tokens/{}'), (f'/accounts/{account}/tokens/verify', None)):
        try:
            token_id = (api.call('GET', verify) or {}).get('id')
        except Failed:
            continue
        paths = [read.format(token_id)] if read else []
        paths.append(f'/accounts/{account}/tokens/{token_id}')
        for path in paths if token_id else []:
            try:
                me = api.call('GET', path) or {}
            except Failed:
                continue
            return [
                str(g.get('name', '')).lower()
                for p in me.get('policies') or []
                for g in p.get('permission_groups') or []
            ]
    return None


def missing_edit_permissions(api, account, keys):
    """Areas the token may read but provably not change (from its own permission list); [] when that list is
    unreadable, which the ordering of setup's steps makes safe."""
    groups = own_permission_groups(api, account)
    if not groups:
        return []
    writes = [g for g in groups if 'write' in g or 'edit' in g]
    return [k for k in keys if k in EDIT_GROUPS and not any(f in g for g in writes for f in EDIT_GROUPS[k])]


def _rules(policy):
    return [sorted(json.dumps(r, sort_keys=True) for r in policy.get(k) or []) for k in ('include', 'require')]


def _destinations(app):
    kept = ({k: v for k, v in d.items() if v not in (None, '')} for d in app.get('destinations') or [])
    return sorted(json.dumps(d, sort_keys=True) for d in kept)


def setup(cfg, plan, config_path, opener=None):
    if cfg['auth']['ingress'] != 'cloudflared' and cfg['auth']['mode'] != 'cloudflare-access':
        raise Failed(f'nothing to set up: auth.mode is {cfg["auth"]["mode"]} with {cfg["auth"]["ingress"]} ingress')
    s = Setup(cfg, api_for(cfg, opener), plan)
    private, tunneled, access = (
        config.private_network(cfg),
        cfg['auth']['ingress'] == 'cloudflared',
        cfg['auth']['mode'] == 'cloudflare-access',
    )
    gaps = s.preflight()
    if gaps:
        raise Needs(stuck_message(s, known_tunnel(s, tunneled), gaps))
    try:
        s.prerequisites()
    except Needs as e:
        raise Needs(stuck_message(s, known_tunnel(s, tunneled), [str(e)])) from None
    tunnel = s.tunnel() if tunneled else ''
    # Make before break: the new way in (routes or DNS, then the Access app) exists before the tunnel switches,
    # and the old way's leftovers (public DNS, the pair hosts' Bypass app, or private routes) go last.
    if tunneled:
        (s.hostname_routes if private else s.dns)(tunnel)
    cf = cfg['cloudflare']
    found = {('cloudflare', 'account_id'): cf['account_id'], ('cloudflare', 'zone'): cf['zone']}
    if access:
        auth = cfg['auth']['cloudflare']
        auth['audience'] = s.access() or auth['audience']
        if private:
            s.enrollment(s.people_policy())
        found[('auth.cloudflare', 'team')] = auth['team']
        found[('auth.cloudflare', 'audience')] = auth['audience']
    if tunneled:
        (s.private_ingress if private else s.ingress)(tunnel)
        s.token(tunnel)
    s.remember(config_path, found)
    if access and (private or cfg['auth']['cloudflare']['require_warp']) and not pair_hosts(cfg):
        s.drop_apps_bypass()  # a Bypass app left from a public setup would be a way around the client
    if tunneled:
        (s.drop_public_dns if private else lambda _t: s.drop_hostname_routes())(tunnel)
    where = 'private: Cloudflare One client only' if private else 'public sign-in page'
    names = signed_in_hosts(cfg) if private else hostnames(cfg)
    say(f'  Cloudflare: {", ".join(names)} -> tunnel {s.name} ({where}); {len(people(cfg))} people may sign in')


def known_tunnel(s, tunneled):
    try:
        return s.find_tunnel() if tunneled else ''
    except Failed:
        return ''


def stuck_message(s, tunnel, gaps):
    """The preflight's gaps, and, when an earlier run left the tunnel switched without its way in finished, that
    the agents are unreachable right now and what brings them back."""
    msg = (
        'before Cloudflare can be set up: '
        + '; '.join(gaps)
        + '. Edited tokens keep their value. Then run agentctl setup again.'
    )
    if not tunnel:
        return msg
    now = s.current_ingress(tunnel)
    private = config.private_network(s.cfg)
    if private and now == 'private':
        return (
            msg + ' Right now the agents are not reachable: an earlier run already switched the tunnel to private. The '
            'next run finishes the private setup; to have the public sign-in page back meanwhile, set '
            '[auth.cloudflare] network = "public" and run agentctl cloudflare setup.'
        )
    if now == 'public':
        return msg + ' Nothing was changed: the current public sign-in page keeps working until then.'
    return msg


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
    'org': 'Account · Access: Organizations → Edit (sets the client session duration only while it has none)',
    'dns': 'Zone · DNS → Edit on the zone',
    # network = "private" (and require_warp): tunnel hostname routes, and the client settings doctor checks
    'routes': 'Account · Cloudflare One Networks → Edit (older dashboards: Cloudflare Tunnel → Edit)',
    'devices': 'Account · Zero Trust → Edit (turns on the Gateway proxy when it is off)',
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
                GATEWAY_PROXY_FIX,
                'error' if private else 'warning',
            )
        )
    except Failed:
        out.append(
            (
                'gateway-proxy',
                True,
                "couldn't read the client settings with this token: check the Gateway proxy is on (Zero Trust → "
                'Traffic policies → Traffic settings)',
                '',
                'info',
            )
        )
    try:
        org = api.call('GET', f'/accounts/{account}/access/organizations') or {}
        out.append(
            (
                'client-session',
                bool(org.get('warp_auth_session_duration')),
                'a Cloudflare One Client authentication session duration is set (client sessions can sign in)',
                CLIENT_SESSION_FIX,
                'error',
            )
        )
    except Failed:
        out.append(('client-session', True, f"couldn't read it: {CLIENT_SESSION_FIX}", '', 'info'))
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
    if private:
        warp_app = next((a for a in apps if a.get('type') == 'warp'), None)
        policies = api.call('GET', f'/accounts/{account}/access/policies') or []
        ours = next((p.get('id') for p in policies if p.get('name') == s.name), None)
        enrolled = bool(warp_app and ours and any(p.get('id') == ours for p in warp_app.get('policies') or []))
        out.append(
            (
                'client-enrollment',
                enrolled,
                "agentlab's people may enroll the Cloudflare One client",
                'agentctl cloudflare setup (adds its policy to device enrollment, keeping the others)',
                'error',
            )
        )
        out += enrollment_exposure(cfg, api, account, apps, s.name)
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


def enrollment_exposure(cfg, api, account, apps, ours):
    """Private mode lets everyone agentlab's policy admits enroll the Cloudflare One client. Read-only warnings about
    what that could open elsewhere in the account: other apps that admit a whole allow_domains domain, and private
    IP routes on other tunnels that no Access application covers. agentlab never changes any of them."""
    out = []
    domains = {d.lower() for d in cfg['auth']['allow_domains']}
    if domains:
        try:
            policies = {p.get('id'): p for p in api.call('GET', f'/accounts/{account}/access/policies') or []}
        except Failed:
            policies = {}
        open_apps = []
        for app in apps:
            if str(app.get('name', '')).startswith(ours) or app.get('type') == 'warp':
                continue  # agentlab's own, and device enrollment (which admits them on purpose)
            rules = [
                r
                for ref in app.get('policies') or []
                for r in (policies.get(ref.get('id')) or ref).get('include') or []
            ]
            hit = sorted({r['email_domain']['domain'].lower() for r in rules if 'email_domain' in r} & domains)
            if hit:
                open_apps.append(f'{app.get("name")} admits everyone @{", @".join(hit)}')
        if open_apps:
            out.append(
                (
                    'enrollment-exposure',
                    False,
                    '; '.join(open_apps) + ': anyone who can enroll the Cloudflare One client (your allow_domains) '
                    'could reach these too',
                    'narrow those applications to the people who need them, or drop allow_domains and list owners; '
                    'agentlab never changes other applications',
                    'warning',
                )
            )
    try:
        routes = api.call('GET', f'/accounts/{account}/teamnet/routes?is_deleted=false') or []
    except Failed:
        return out
    covered = [
        ipaddress.ip_network(d['cidr'], strict=False)
        for a in apps
        for d in a.get('destinations') or []
        if d.get('type') == 'private' and d.get('cidr')
    ]
    bare = []
    for r in routes:
        try:
            net = ipaddress.ip_network(r.get('network', ''), strict=False)
        except ValueError:
            continue
        if not any(net.version == c.version and net.subnet_of(c) for c in covered):
            bare.append(f'{net} ({r.get("tunnel_name") or r.get("tunnel_id") or "a tunnel"})')
    if bare:
        out.append(
            (
                'uncovered-routes',
                True,
                'private routes with no Access application in front: ' + ', '.join(bare) + ' (enrolled client '
                'devices reach them unless a Gateway network policy stops them)',
                '',
                'info',
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
