"""Cloudflare tunnel, DNS and Access setup for network = "private" (default, WARP client only) or "public"."""

import ipaddress
import json
import os
import socket
import ssl
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Any, Literal, NamedTuple, NotRequired, Protocol, TypedDict

from . import config, gateway, render, tomledit
from .config import Cluster
from .fsm import Machine
from .util import Failed, Json, Needs, Plan, say, warn, write_if_changed

API = 'https://api.cloudflare.com/client/v4'

Reply = Any  # Cloudflare's `result`: an object, a list of them, a string (tunnel token) or None
Method = Literal['GET', 'POST', 'PUT', 'PATCH', 'DELETE']
PermissionKey = Literal['tunnels', 'dns', 'access', 'idps', 'org', 'routes', 'devices']
Severity = Literal['error', 'warning', 'info']
Fact = tuple[str, bool, str, str, Severity]  # a doctor check: (id, ok, message, fix, severity)
IngressState = Literal['private', 'public', '']


class _Response(Protocol):
    def read(self) -> bytes: ...


class Opener(Protocol):
    """urllib.request.urlopen, or a test's stand-in."""

    def __call__(self, url: urllib.request.Request, *, timeout: float) -> AbstractContextManager[_Response]: ...


class IngressRule(TypedDict, total=False):
    hostname: str
    service: str


class WarpRouting(TypedDict):
    enabled: bool


TunnelConfig = TypedDict('TunnelConfig', {'ingress': list[IngressRule], 'warp-routing': WarpRouting})


class DnsRecord(TypedDict):
    type: Literal['CNAME']
    name: str
    content: str
    proxied: bool
    comment: str


class HostnameRoute(TypedDict):
    hostname: str
    tunnel_id: str
    comment: str


class AccessPolicy(TypedDict):
    name: str
    decision: Literal['allow', 'bypass']
    include: list[Json]  # Cloudflare's rule objects, e.g. {'email': {'email': ...}}
    require: list[Json]


class PolicyRef(TypedDict):
    id: str
    precedence: int


class Destination(TypedDict, total=False):
    type: Literal['private', 'public']
    hostname: str
    port_range: str
    uri: str


class SelfHostedApp(TypedDict):
    name: str
    type: Literal['self_hosted']
    destinations: list[Destination]
    session_duration: str
    app_launcher_visible: bool
    policies: list[PolicyRef]
    allowed_idps: list[str]
    auto_redirect_to_identity: bool
    allow_authenticate_via_warp: NotRequired[bool]
    domain: NotRequired[str]


class OidcClient(TypedDict):
    auth_type: Literal['oidc']
    redirect_uris: list[str]
    grant_types: list[str]
    scopes: list[str]
    allow_pkce_without_client_secret: bool
    client_id: NotRequired[str]


class SaasApp(TypedDict):
    name: str
    type: Literal['saas']
    app_launcher_visible: bool
    policies: list[PolicyRef]
    allowed_idps: list[str]
    auto_redirect_to_identity: bool
    allow_authenticate_via_warp: NotRequired[bool]
    saas_app: OidcClient


class ReauthGap(NamedTuple):
    profile: str  # the device profile, as shown to people
    path: str  # its Include list's API path
    have: list[Json]  # its Include list now
    missing: list[str]  # hosts it lacks


class ApiError(Failed):
    """A refused Cloudflare call; `status` is the HTTP status (0 when Cloudflare answered 200 with success: false)."""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


EDGE = 'http://127.0.0.1:8088'


class Api:
    def __init__(self, token: str, opener: Opener | None = None) -> None:
        self.token = token
        self.opener: Opener = opener or urllib.request.urlopen

    def call(self, method: Method, path: str, body: object = None) -> Reply:
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


def hostnames(cfg: Cluster) -> list[str]:
    return render.public_hosts(cfg)


def signed_in_hosts(cfg: Cluster) -> list[str]:
    return [h for h in (cfg['domain'], cfg['hub_domain'], cfg['coolify_domain']) if h]


def pair_hosts(cfg: Cluster) -> list[str]:
    return [a['pair_host'] for a in cfg['agents'] if a['pair_host']]


def private_hosts(cfg: Cluster) -> list[str]:
    return signed_in_hosts(cfg) + pair_hosts(cfg)


CALLBACK = '/_agentlab/oidc/callback'  # must match gate/gate/oidc.py
GATE_FILES = {'client_id': 'oidc-client-id', 'client_secret': 'oidc-client-secret', 'key': 'session.key'}
LIVE = 'https-live'
CERT_WAIT, CERT_WARN_DAYS = 180, 14

HttpsState = Literal['off', 'sign_in', 'port_443', 'live', 'broken']

# Private HTTPS, rolled out step by step (setup, then apply's finish_https) and turned off the same way back. It lives
# in Cloudflare and a file, so its state is read from what exists (HttpsFacts); every write that changes one of those
# must be a move HTTPS allows (Setup.https_move).
#   off       no sign-in app                         sign_in  the gate's OIDC app exists; Access covers port 80 only
#   port_443  Access covers 443 too                  live     the gate redirects plain HTTP (the https-live marker)
#   broken    a mix no move leads to (443 without the sign-in app, the marker without 443): setup repairs it
HTTPS: Machine[HttpsState] = Machine(
    'https',
    {
        'off': ('sign_in',),
        'sign_in': ('port_443', 'off'),
        'port_443': ('live', 'sign_in'),
        'live': ('port_443',),
        'broken': ('off', 'sign_in', 'port_443', 'live'),
    },
)


class HttpsFacts(NamedTuple):
    """What the HTTPS rollout is made of."""

    sign_in: bool  # agentlab's OIDC application for the gate
    port_443: bool  # a port 443 destination in the people's app
    live: bool  # the https-live marker

    def state(self) -> HttpsState:
        if self.live:
            return 'live' if self.port_443 and self.sign_in else 'broken'
        if self.port_443:
            return 'port_443' if self.sign_in else 'broken'
        return 'sign_in' if self.sign_in else 'off'


class HttpsNotReady(Failed):
    """finish_https can't take the next step yet; HTTPS stays as it is and apply carries on."""


class People(NamedTuple):
    """Setup.access(): the people's app's audience, and whether it covers port 443."""

    aud: str
    port_443: bool


def _port_443(app: Mapping[str, Any] | None) -> bool:
    return any(d.get('port_range') == '443' for d in (app or {}).get('destinations') or [])


def gate_dir(cfg: Cluster) -> str:
    return f'{cfg["data"]}/{render.GATE_SECRETS_DIR}'


def gate_secret(cfg: Cluster, name: str) -> str:
    try:
        with open(f'{gate_dir(cfg)}/{GATE_FILES.get(name, name)}') as f:
            return f.read().strip()
    except OSError:
        return ''


def save_gate_secret(cfg: Cluster, name: str, value: str) -> bool:
    """Write a gate secret readable only by the gate's uid."""
    folder = gate_dir(cfg)
    os.makedirs(folder, mode=0o700, exist_ok=True)
    path = f'{folder}/{GATE_FILES.get(name, name)}'
    changed = write_if_changed(path, value, mode=0o400)
    if os.name == 'posix' and os.geteuid() == 0:
        for p, mode in ((path, 0o400), (folder, 0o500)):
            os.chown(p, render.GATE_UID, render.GATE_UID)
            os.chmod(p, mode)
    return changed


def edge_certificate(
    host: str, address: str = render.EDGE_IP, port: int = 443, timeout: float = 5
) -> tuple[int | None, str]:
    """(days the edge's certificate for `host` stays valid, '') when trusted, else (None, why)."""
    ctx = ssl.create_default_context()
    try:
        with (
            socket.create_connection((address, port), timeout=timeout) as raw,
            ctx.wrap_socket(raw, server_hostname=host) as tls,
        ):
            cert = tls.getpeercert()
    except (OSError, ssl.SSLError) as e:
        return None, str(e)
    not_after = (cert or {}).get('notAfter')
    if not isinstance(not_after, str):
        return None, 'the certificate names no expiry'
    left = (ssl.cert_time_to_seconds(not_after) - time.time()) / 86400
    return int(left), ''


def edge_redirect(host: str, address: str = render.EDGE_IP, port: int = 80, timeout: float = 5) -> tuple[bool, str]:
    """(True, '') when plain HTTP for `host` on the edge redirects to https, else (False, what came back)."""
    request = f'GET / HTTP/1.1\r\nHost: {host}\r\nAccept: text/html\r\nConnection: close\r\n\r\n'.encode()
    try:
        with socket.create_connection((address, port), timeout=timeout) as raw:
            raw.sendall(request)
            head = raw.recv(4096).decode('latin-1')
    except OSError as e:
        return False, str(e)
    status = head.split(' ', 2)[1] if head.count(' ') >= 2 else '?'
    lines = head.split('\r\n')
    location = next((x.split(':', 1)[1].strip() for x in lines if x.lower().startswith('location:')), '')
    if status in ('301', '302', '307', '308') and location.startswith(f'https://{host}/'):
        return True, ''
    return False, f'HTTP {status}' + (f' to {location}' if location else ' without a redirect')


def people(cfg: Cluster) -> list[str]:
    return render.people(cfg)


def configured(cfg: Cluster) -> bool:
    return os.path.isfile(cfg['cloudflare']['api_token_file'])


def api_for(cfg: Cluster, opener: Opener | None = None) -> Api:
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


def zone_of(api: Api, host: str) -> Json | None:
    """The zone serving `host`: the longest of its parent names this token can see."""
    labels = host.split('.')
    for i in range(len(labels) - 1):
        zones = api.call('GET', f'/zones?name={".".join(labels[i:])}') or []
        if zones:
            return zones[0]
    return None


def discover(cfg: Cluster, api: Api) -> None:
    """Fill in the zone, account and Zero Trust team the config leaves out (in memory only)."""
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

    def __init__(self, cfg: Cluster, api: Api, plan: Plan) -> None:
        self.cfg, self.api, self.plan = cfg, api, plan
        self.account = cfg['cloudflare']['account_id']
        self.name = f'agentlab-{cfg["name"]}'

    def write(self, what: str, method: Method, path: str, body: object = None) -> Reply:
        if self.plan.dry:
            self.plan.do(f'{what}: {method} {path}')
            return None
        try:
            result = self.api.call(method, path, body)
        except ApiError as e:
            raise refused(e, what) or e from None
        self.plan.do(what)
        return result

    def find_tunnel(self) -> str:
        found = self.api.call('GET', f'/accounts/{self.account}/cfd_tunnel?name={self.name}&is_deleted=false') or []
        return found[0]['id'] if found else ''

    def tunnel(self) -> str:
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

    def ingress(self, tunnel: str) -> None:
        want: list[IngressRule] = [{'hostname': h, 'service': EDGE} for h in hostnames(self.cfg)]
        want += [{'service': 'http_status:404'}]
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

    def token(self, tunnel: str) -> None:
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

    def dns(self, tunnel: str) -> None:
        zone_name = self.cfg['cloudflare']['zone']
        zones = self.api.call('GET', f'/zones?name={zone_name}') or []
        if not zones:
            raise Failed(f'zone {zone_name} not found for this API token')
        zone = zones[0]['id']
        target = f'{tunnel}.cfargotunnel.com'
        for host in hostnames(self.cfg):
            records = self.api.call('GET', f'/zones/{zone}/dns_records?name={host}') or []
            body: DnsRecord = {'type': 'CNAME', 'name': host, 'content': target, 'proxied': True, 'comment': self.name}
            same = [r for r in records if r.get('type') == 'CNAME' and r.get('content') == target and r.get('proxied')]
            if same:
                continue
            if records:
                if len(records) > 1 or records[0].get('type') != 'CNAME':
                    raise Failed(f"{host} already has DNS records that are not this tunnel's CNAME; remove them first")
                self.write(f'point {host} at the tunnel', 'PUT', f'/zones/{zone}/dns_records/{records[0]["id"]}', body)
            else:
                self.write(f'add DNS {host} -> tunnel', 'POST', f'/zones/{zone}/dns_records', body)

    def policy(
        self,
        name: str,
        decision: Literal['allow', 'bypass'],
        include: list[Json],
        describe: str,
        require: Sequence[Json] = (),
    ) -> str:
        body: AccessPolicy = {
            'name': self.named(name),
            'decision': decision,
            'include': include,
            'require': list(require),
        }
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

    def people_policy(self) -> str:
        include: list[Json] = [{'email': {'email': e}} for e in people(self.cfg)]
        domains: list[Json] = [{'email_domain': {'domain': d}} for d in self.cfg['auth']['allow_domains']]
        describe = f'to {len(include)} people' + (f' and {len(domains)} email domains' if domains else '')
        require: list[Json] = []
        if self.cfg['auth']['cloudflare']['require_warp']:
            require = [{'device_posture': {'integration_uid': self.gateway_check()}}]
            describe += ' on the Cloudflare One client'
        return self.policy('', 'allow', include + domains, describe, require)

    def gateway_check(self) -> str:
        """The account's Gateway device posture check that Access policies require by id; created when missing."""
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

    def app(
        self,
        name: str,
        hosts: list[str],
        policy: str,
        idps: list[str],
        private: bool = False,
        destinations: list[Destination] | None = None,
    ) -> str:
        destinations = destinations or (
            [{'type': 'private', 'hostname': h, 'port_range': '80'} for h in hosts]
            if private
            else [{'type': 'public', 'uri': h} for h in hosts]
        )
        # Client sign-in per app, unless the account already enables it for all apps (then the flag is refused, #21).
        warp = (private or self.cfg['auth']['cloudflare']['require_warp']) and not self.account_allows_client_sign_in()
        body: SelfHostedApp = {
            'name': self.named(name),
            'type': 'self_hosted',
            'destinations': destinations,
            'session_duration': '24h',
            'app_launcher_visible': False,
            'policies': [{'id': policy, 'precedence': 1}],
            # Empty offers every login method and clears an earlier pin.
            'allowed_idps': idps,
            'auto_redirect_to_identity': len(idps) == 1,
        }
        if warp:  # left out otherwise: a PUT replaces the rest
            body['allow_authenticate_via_warp'] = True
        if not private:  # private apps have no public destination to name as `domain`
            body['domain'] = hosts[0]
        apps = self.apps()
        found = next((a for a in apps if a.get('name') == body['name']), None)
        if not name:  # the people's app: whether it covers 443 is a step of the HTTPS rollout
            facts = self.https_facts(apps)
            self.https_move(facts, facts._replace(port_443=_port_443(body)))
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

    def account_allows_client_sign_in(self) -> bool:
        if not hasattr(self, '_org_sign_in'):
            try:
                org = self.api.call('GET', f'/accounts/{self.account}/access/organizations') or {}
            except (ApiError, Failed):
                org = {}
            self._org_sign_in = bool(org.get('allow_authenticate_via_warp'))
        return self._org_sign_in

    def named(self, name: str) -> str:
        """agentlab only touches resources named agentlab-<cluster>[-suffix]."""
        return f'{self.name} {name}' if name else self.name

    def access(self, sign_in: bool = False, ready: bool | None = None) -> People:
        """The people's Access application (public: plus the pair hosts' Bypass app); 443 joins once https_ready(),
        or `ready` when the caller already asked."""
        providers = self.api.call('GET', f'/accounts/{self.account}/access/identity_providers') or []
        idps = login_methods(self.cfg, providers)
        private = config.private_network(self.cfg)
        policy = self.people_policy()
        if sign_in:
            self.sign_in_app(policy, idps)
        destinations: list[Destination] | None = None
        ports = ['80']
        if private:
            if config.private_https(self.cfg) and (self.https_ready() if ready is None else ready):
                ports = ['80', '443']
            destinations = [
                {'type': 'private', 'hostname': h, 'port_range': p} for h in signed_in_hosts(self.cfg) for p in ports
            ]
            destinations += [
                {'type': 'private', 'hostname': h, 'port_range': '443'} for h in pair_hosts(self.cfg) if '443' in ports
            ]
        aud = self.app('', signed_in_hosts(self.cfg), policy, idps, private=private, destinations=destinations)
        if pair_hosts(self.cfg) and not private:
            bypass = self.policy('apps', 'bypass', [{'everyone': {}}], 'for the T3 apps (bypass)')
            self.app('apps', pair_hosts(self.cfg), bypass, [])
        return People(aud, '443' in ports)

    def apps(self) -> list[Json]:
        """The account's Access applications."""
        return self.api.call('GET', f'/accounts/{self.account}/access/apps') or []

    def people_app(self) -> Json | None:
        return next((a for a in self.apps() if a.get('name') == self.name), None)

    def https_facts(self, apps: list[Json]) -> HttpsFacts:
        """The HTTPS rollout as `apps` (one read of the account's Access applications) and the marker show it."""
        return HttpsFacts(
            sign_in=any(a.get('name') == self.named('sign-in') for a in apps),
            port_443=_port_443(next((a for a in apps if a.get('name') == self.name), None)),
            live=os.path.exists(f'{gate_dir(self.cfg)}/{LIVE}'),
        )

    def https_move(self, before: HttpsFacts, after: HttpsFacts) -> None:
        """Refuse a write that would take the rollout somewhere HTTPS doesn't allow (a dry run moves nothing)."""
        if not self.plan.dry and after.state() != before.state():
            HTTPS.to(before.state(), after.state())

    def https_ready(self) -> bool:
        """Whether 443 may join the people's app: already joined (never taken back), or every signed-in name has a trusted cert."""
        has = _port_443(self.people_app())
        return has or all(edge_certificate(h)[0] is not None for h in signed_in_hosts(self.cfg))

    def sign_in_app(self, policy: str, idps: list[str]) -> None:
        """The Access for SaaS OIDC app the gate signs in with; its secret is shown only at creation, so a lost one means a new app."""
        hosts = signed_in_hosts(self.cfg)
        warp = not self.account_allows_client_sign_in()
        saas: OidcClient = {
            'auth_type': 'oidc',
            'redirect_uris': [f'https://{h}{CALLBACK}' for h in hosts],
            'grant_types': ['authorization_code_with_pkce'],
            'scopes': ['openid', 'email', 'profile'],
            'allow_pkce_without_client_secret': False,
        }
        body: SaasApp = {
            'name': self.named('sign-in'),
            'type': 'saas',
            'app_launcher_visible': False,
            'policies': [{'id': policy, 'precedence': 1}],
            'allowed_idps': idps,
            'auto_redirect_to_identity': len(idps) == 1,
            'saas_app': saas,
        }
        if warp:  # left out otherwise: a PUT replaces the rest
            body['allow_authenticate_via_warp'] = True
        apps = self.apps()
        named = [a for a in apps if a.get('name') == body['name']]
        mine = gate_secret(self.cfg, 'client_id')
        found = next((a for a in named if mine and (a.get('saas_app') or {}).get('client_id') == mine), None)
        if found and not gate_secret(self.cfg, 'client_secret'):
            found = None
        if found:
            have = found.get('saas_app') or {}
            if (
                sorted(have.get('redirect_uris') or []) != sorted(saas['redirect_uris'])
                or sorted(have.get('scopes') or []) != sorted(saas['scopes'])
                or sorted(have.get('grant_types') or []) != sorted(saas['grant_types'])
                or [p.get('id') for p in found.get('policies') or []] != [policy]
                or sorted(found.get('allowed_idps') or []) != sorted(idps)
                or bool(found.get('allow_authenticate_via_warp')) != warp
            ):
                body['saas_app'] = {**saas, 'client_id': mine}  # a PUT replaces the app: keep its client
                self.write(
                    f'update Access application {body["name"]} (OIDC sign-in for the gate)',
                    'PUT',
                    f'/accounts/{self.account}/access/apps/{found["id"]}',
                    body,
                )
        else:
            facts = self.https_facts(apps)
            self.https_move(facts, facts._replace(sign_in=True))
            made = self.write(
                f'create Access application {body["name"]} (OIDC sign-in for the gate): ' + ', '.join(hosts),
                'POST',
                f'/accounts/{self.account}/access/apps',
                body,
            )
            client = (made or {}).get('saas_app') or {}
            if made and not (client.get('client_id') and client.get('client_secret')):
                raise Failed(f'Cloudflare made {body["name"]} but returned no client id and secret: run setup again')
            if made:
                save_gate_secret(self.cfg, 'client_id', client['client_id'])
                save_gate_secret(self.cfg, 'client_secret', client['client_secret'])
                self.plan.do(f'saved its client id and secret to {gate_dir(self.cfg)} (only the gate reads them)')
        for old in (a for a in named if a is not found):
            self.write(
                f'remove the replaced Access application {old["name"]} ({(old.get("saas_app") or {}).get("client_id")})',
                'DELETE',
                f'/accounts/{self.account}/access/apps/{old["id"]}',
            )

    def drop_sign_in(self) -> None:
        """https turned off: agentlab's own OIDC application goes (after the people's app is back to port 80)."""
        apps = self.apps()
        facts = self.https_facts(apps)
        for app in (a for a in apps if a.get('name') == self.named('sign-in')):
            self.https_move(facts, facts._replace(sign_in=False))
            path = f'/accounts/{self.account}/access/apps/{app["id"]}'
            self.write(f'remove Access application {app["name"]} (https is off)', 'DELETE', path)

    def mark_live(self, on: bool) -> None:
        """The gate redirects HTTP to HTTPS only while this marker file exists."""
        path = f'{gate_dir(self.cfg)}/{LIVE}'
        if not on:  # always a legal move: only live and broken have the marker, and both may drop it
            if os.path.exists(path):
                self.plan.do('stop redirecting plain HTTP to HTTPS', fn=lambda: os.remove(path))
            return
        if os.path.exists(path):
            return
        apps = self.apps()
        app = next((a for a in apps if a.get('name') == self.name), None) or {}
        covered = {d.get('hostname') for d in app.get('destinations') or [] if d.get('port_range') == '443'}
        if set(private_hosts(self.cfg)) <= covered and all(gate_secret(self.cfg, k) for k in GATE_FILES):
            facts = self.https_facts(apps)
            self.https_move(facts, facts._replace(live=True))
            self.plan.do(
                'redirect plain HTTP to HTTPS (Access covers port 443)',
                fn=lambda: save_gate_secret(self.cfg, LIVE, time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())),
            )

    def drop_apps_bypass(self) -> None:
        apps = self.api.call('GET', f'/accounts/{self.account}/access/apps') or []
        for app in (a for a in apps if a.get('name') == self.named('apps')):
            path = f'/accounts/{self.account}/access/apps/{app["id"]}'
            self.write(f'remove Access application {app["name"]} (bypass)', 'DELETE', path)
        policies = self.api.call('GET', f'/accounts/{self.account}/access/policies') or []
        for p in (p for p in policies if p.get('name') == self.named('apps')):
            self.write(
                f'remove Access policy {p["name"]}', 'DELETE', f'/accounts/{self.account}/access/policies/{p["id"]}'
            )

    def private_ingress(self, tunnel: str) -> None:
        want: TunnelConfig = {'ingress': [{'service': 'http_status:404'}], 'warp-routing': {'enabled': True}}
        path = f'/accounts/{self.account}/cfd_tunnel/{tunnel}/configurations'
        current = None if tunnel.startswith('<') else self.api.call('GET', path)
        have = (current or {}).get('config') or {}
        ingress = [{k: r.get(k) for k in ('hostname', 'service') if r.get(k)} for r in have.get('ingress') or []]
        if ingress != want['ingress'] or not (have.get('warp-routing') or {}).get('enabled'):
            self.write('set the tunnel to private routing only (no public hostnames)', 'PUT', path, {'config': want})

    def hostname_routes(self, tunnel: str) -> None:
        """A private hostname route per name; stale agentlab routes go, another owner's route on a name stops setup."""
        path = f'/accounts/{self.account}/zerotrust/routes/hostname'
        try:
            routes = self.api.call('GET', path) or []
        except ApiError as e:
            if e.status not in (401, 403):
                raise
            raise Needs(f'the token may not manage tunnel hostname routes: add "{PERMISSIONS["routes"]}"') from None
        hosts = private_hosts(self.cfg)
        for host in hosts:
            same = [r for r in routes if r.get('hostname') == host]
            if any(r.get('tunnel_id') == tunnel for r in same):
                continue
            if any(r.get('comment') != self.name for r in same):
                raise Failed(f"{host} already has a hostname route to another tunnel (not agentlab's): remove it first")
            for r in same:
                self.write(f'remove the old route for {host}', 'DELETE', f'{path}/{r["id"]}')
            body: HostnameRoute = {'hostname': host, 'tunnel_id': tunnel, 'comment': self.name}
            self.write(f'route {host} over the tunnel (private hostname)', 'POST', path, body)
        for r in routes:
            if r.get('comment') == self.name and r.get('hostname') not in hosts:
                self.write(f'remove the route for {r["hostname"]}', 'DELETE', f'{path}/{r["id"]}')

    def drop_public_dns(self, tunnel: str) -> None:
        """Remove the public DNS records agentlab made (by comment, pointing at its tunnel); others stay."""
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

    def remember(self, config_path: str, values: Mapping[tuple[str, str], str]) -> None:
        """Write discovered values into cluster.toml (the gate reads team and audience from there)."""
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

    def drop_hostname_routes(self) -> None:
        """Back to public: agentlab's own private hostname routes (by comment) go; anyone else's stay."""
        path = f'/accounts/{self.account}/zerotrust/routes/hostname'
        try:
            routes = self.api.call('GET', path) or []
        except ApiError as e:
            if e.status not in (401, 403):
                raise
            return
        for r in routes:
            if r.get('comment') == self.name:
                self.write(f'remove the private route for {r["hostname"]}', 'DELETE', f'{path}/{r["id"]}')

    def current_ingress(self, tunnel: str) -> IngressState:
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

    def preflight(self) -> list[str]:
        """Read-only check of everything the run needs, before any change (dry runs too); a gap is exit 2 with the fix."""
        gaps: list[str] = []
        cfg, account = self.cfg, self.account
        private = config.private_network(cfg)
        warp = private or cfg['auth']['cloudflare']['require_warp']
        reads: list[tuple[PermissionKey, str]] = []
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
            reads += [('devices', f'/accounts/{account}/gateway/rules')]
        if warp:
            reads += [('devices', f'/accounts/{account}/devices/settings')]
        answers: dict[str, Reply] = {}
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

    def prerequisites(self) -> None:
        """Turn on the account settings clients need, only when off or unset (never shorten the session or disable the proxy)."""
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
        for name, path, have, missing in reauth_gaps(self.cfg, self.api, self.account, org):
            added = [{'host': h, 'description': 'agentlab: client re-authentication'} for h in missing]
            self.write(
                f'add {", ".join(missing)} to the Include list of the {name} device profile (re-authentication goes '
                'through the client; nothing is removed)',
                'PUT',
                path,
                [*have, *added],
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

    def enrollment(self, policy: str) -> None:
        """Append agentlab's policy to the account's device enrollment app, after the existing ones (kept in order)."""
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


def refused(e: ApiError, what: str) -> Needs | None:
    """A change Cloudflare refused that a person must fix, as Needs with the fix; None for anything else."""
    text = str(e)
    # by Cloudflare's message only: 12130 is its code for any invalid request
    if 'allow_authenticate_via_warp cannot be set' in text:
        return Needs(
            f'Cloudflare refused to {what}: {CLIENT_SESSION_FIX}. Then run agentctl setup again. '
            f'(Cloudflare said: {text})'
        )
    if e.status in (401, 403):
        key = permission_for(text)
        add = f'add "{PERMISSIONS[key]}" to the token' if key else 'give the token the permission for it'
        return Needs(
            f'Cloudflare refused to {what} (HTTP {e.status}): {add} in the dashboard (its value stays the same), '
            f'then run agentctl setup again. (Cloudflare said: {text})'
        )
    return None


def permission_for(text: str) -> PermissionKey | Literal['']:
    areas: tuple[tuple[str, PermissionKey], ...] = (
        ('/zerotrust/routes', 'routes'),
        ('/cfd_tunnel', 'tunnels'),
        ('/dns_records', 'dns'),
        ('/access/organizations', 'org'),
        ('/identity_providers', 'idps'),
        ('/access/', 'access'),
        ('/devices/', 'devices'),
    )
    for fragment, key in areas:
        if fragment in text:
            return key
    return ''


# Permission-group name fragments meaning "may change" each area; generous on purpose, so unknown names never block.
EDIT_GROUPS: dict[PermissionKey, tuple[str, ...]] = {
    'tunnels': ('tunnel', 'connector', 'cloudflared'),
    'dns': ('dns',),
    'access': ('access: apps', 'access: policies', 'access: apps and policies'),
    'routes': ('cloudflare one networks', 'networks', 'tunnel', 'zero trust'),
}


def own_permission_groups(api: Api, account: str) -> list[str] | None:
    """The names of the token's permission groups, or None when the token may not read itself (the usual case)."""
    places: tuple[tuple[str, str | None], ...] = (
        ('/user/tokens/verify', '/user/tokens/{}'),
        (f'/accounts/{account}/tokens/verify', None),
    )
    for verify, read in places:
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


def missing_edit_permissions(api: Api, account: str, keys: Iterable[PermissionKey]) -> list[PermissionKey]:
    """Areas the token may read but provably not change; [] when its permission list is unreadable."""
    groups = own_permission_groups(api, account)
    if not groups:
        return []
    writes = [g for g in groups if 'write' in g or 'edit' in g]
    return [k for k in keys if k in EDIT_GROUPS and not any(f in g for g in writes for f in EDIT_GROUPS[k])]


def _rules(policy: Mapping[str, Any]) -> list[list[str]]:
    return [sorted(json.dumps(r, sort_keys=True) for r in policy.get(k) or []) for k in ('include', 'require')]


def _destinations(app: Mapping[str, Any]) -> list[str]:
    kept = ({k: v for k, v in d.items() if v not in (None, '')} for d in app.get('destinations') or [])
    return sorted(json.dumps(d, sort_keys=True) for d in kept)


def setup(cfg: Cluster, plan: Plan, config_path: str, opener: Opener | None = None) -> None:
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
    # Make before break: the new way in exists before the tunnel switches; the old way's leftovers go last.
    if tunneled:
        (s.hostname_routes if private else s.dns)(tunnel)
    cf = cfg['cloudflare']
    found: dict[tuple[str, str], str] = {
        ('cloudflare', 'account_id'): cf['account_id'],
        ('cloudflare', 'zone'): cf['zone'],
    }
    https = config.private_https(cfg)
    port_443 = False
    if access:
        if not https and not plan.dry:
            s.mark_live(False)  # the redirect stops before Access stops covering 443
        auth = cfg['auth']['cloudflare']
        # the sign-in app and the gate's client must exist before 443 joins the people's app
        people_app = s.access(sign_in=https)
        auth['audience'], port_443 = people_app.aud or auth['audience'], people_app.port_443
        if private:
            s.enrollment(s.people_policy())
            seen = gateway.ensure(s)
            say(f"  Gateway: agentlab's rule sits ahead of the account's {seen['rules']} own")
        else:
            gateway.drop(s)
        found[('auth.cloudflare', 'team')] = auth['team']
        found[('auth.cloudflare', 'audience')] = auth['audience']
    if tunneled:
        (s.private_ingress if private else s.ingress)(tunnel)
        s.token(tunnel)
    s.remember(config_path, found)
    if access and (private or (cfg['auth']['cloudflare']['require_warp'] and not pair_hosts(cfg))):
        s.drop_apps_bypass()  # a Bypass app left from a public setup would be a way around the client
    if tunneled:
        (s.drop_public_dns if private else lambda _t: s.drop_hostname_routes())(tunnel)
    if access and https and not plan.dry:
        s.mark_live(True)
    if access and not https:
        s.drop_sign_in()
    where = 'private: Cloudflare One client only' if private else 'public sign-in page'
    if https:
        where += ', HTTPS' if port_443 else ', HTTPS once the edge has its certificate (agentctl apply)'
    names = private_hosts(cfg) if private else hostnames(cfg)
    say(f'  Cloudflare: {", ".join(names)} -> tunnel {s.name} ({where}); {len(people(cfg))} people may sign in')


def known_tunnel(s: Setup, tunneled: bool) -> str:
    try:
        return s.find_tunnel() if tunneled else ''
    except Failed:
        return ''


def stuck_message(s: Setup, tunnel: str, gaps: list[str]) -> str:
    """The preflight's gaps, plus a note when an earlier run left the tunnel switched without its way in."""
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


def finish_https(
    cfg: Cluster,
    plan: Plan,
    opener: Opener | None = None,
    wait: float = CERT_WAIT,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """After apply: once the edge's certificate is trusted, add 443 to the people's app and start redirecting HTTP."""
    if not config.private_https(cfg) or not configured(cfg) or plan.dry:
        return
    if not all(gate_secret(cfg, k) for k in ('client_id', 'client_secret')):
        say('  HTTPS: the sign-in application is not set up yet: run agentctl cloudflare setup')
        return
    s = Setup(cfg, api_for(cfg, opener), plan)
    apps = s.apps()
    if not any(a.get('name') == s.name for a in apps):
        return
    if not s.https_facts(apps).sign_in:  # deleted by hand: 443 may not join (HTTPS refuses it), setup makes it again
        raise HttpsNotReady('the sign-in app is missing; run `agentctl cloudflare setup`')
    deadline = time.monotonic() + wait
    ready = s.https_ready()
    while not ready and time.monotonic() < deadline:
        sleep(10)
        ready = s.https_ready()
    if not ready:
        why = edge_certificate(cfg['domain'])[1]
        say(
            f'  HTTPS: the edge has no trusted certificate for {cfg["domain"]} yet ({why}); plain HTTP keeps '
            'working. The edge log says why (docker logs of the edge); agentctl apply tries again.'
        )
        return
    s.access(ready=True)
    s.mark_live(True)


def sync_people(cfg: Cluster, plan: Plan, opener: Opener | None = None) -> None:
    """On apply: keep the Access policy equal to owners + admins, once `cloudflare setup` has created it."""
    if cfg['auth']['mode'] != 'cloudflare-access' or not configured(cfg):
        return
    s = Setup(cfg, api_for(cfg, opener), plan)
    policies = s.api.call('GET', f'/accounts/{s.account}/access/policies') or []
    if any(p.get('name') == s.named('') for p in policies):
        s.people_policy()
        if config.private_network(cfg):
            try:
                gateway.ensure(s)
            except Failed as e:  # an apply or update never stops here; `cloudflare setup` shows the details
                warn(f'Gateway rules not updated: {e}')


def login_methods(cfg: Cluster, providers: list[Json]) -> list[str]:
    """Identity provider ids people may use: the pinned login_method, else the account's only one, else [] (all)."""
    wanted = cfg['cloudflare'].get('login_method') or ''
    if wanted:
        match = [i['id'] for i in providers if str(i.get('name', '')).strip().lower() == wanted.strip().lower()]
        if not match:
            names = ', '.join(repr(i.get('name')) for i in providers) or 'none'
            raise Failed(f'[auth.cloudflare] login_method {wanted!r} is not a login method of this account ({names})')
        return match[:1]
    return [providers[0]['id']] if len(providers) == 1 and providers[0].get('id') else []


def idp_hosts(cfg: Cluster, providers: list[Json]) -> list[str]:
    ids: Collection[str | None] = login_methods(cfg, providers) or [p.get('id') for p in providers]
    hosts: list[str] = []
    for p in providers:
        if p.get('id') not in ids:
            continue
        conf, kind = p.get('config') or {}, str(p.get('type', ''))
        url = conf.get('auth_url') or conf.get('sso_target_url') or ''
        host = {
            'google': 'accounts.google.com',
            'google-apps': 'accounts.google.com',
            'azureAD': 'login.microsoftonline.com',
            'github': 'github.com',
            'okta': urllib.parse.urlsplit(conf.get('okta_account') or '').hostname,
        }.get(kind) or urllib.parse.urlsplit(url).hostname
        if host:
            hosts.append(host)
    return list(dict.fromkeys(hosts))


def reauth_gaps(cfg: Cluster, api: Api, account: str, org: Json) -> list[ReauthGap]:
    """[(profile, include path, its list, missing hosts)]: Include-mode profiles lacking hosts needed to re-authenticate."""
    if not (config.private_network(cfg) or cfg['auth']['cloudflare']['require_warp']):
        return []
    providers = api.call('GET', f'/accounts/{account}/access/identity_providers') or []
    team = org.get('auth_domain') or f'{cfg["auth"]["cloudflare"]["team"]}.cloudflareaccess.com'
    want = [team, *idp_hosts(cfg, providers)]
    base = f'/accounts/{account}/devices/policy'
    profiles: list[tuple[str, str, Json]] = [('default', f'{base}/include', api.call('GET', base) or {})]
    for p in api.call('GET', f'/accounts/{account}/devices/policies') or []:
        if not p.get('default'):
            profiles.append((repr(p.get('name') or p.get('policy_id')), f'{base}/{p.get("policy_id")}/include', p))
    gaps: list[ReauthGap] = []
    for name, path, profile in profiles:
        have = profile.get('include')
        if not have or profile.get('exclude'):
            continue
        missing = [h for h in want if not any(e.get('host') == h for e in have)]
        if missing:
            gaps.append(ReauthGap(name, path, have, missing))
    return gaps


# Token permissions per area, named as the dashboard's token page shows them.
PERMISSIONS: dict[PermissionKey, str] = {
    'tunnels': 'Account · Cloudflare One Connector: cloudflared → Edit',
    'access': 'Account · Access: Apps and Policies → Edit (newer dashboards: Access: Apps → Edit, Access: Policies → Edit)',
    'idps': 'Account · Access: Identity Providers → Read',
    'org': 'Account · Access: Organizations → Edit (sets the client session duration only while it has none)',
    'dns': 'Zone · DNS → Edit on the zone',
    'routes': 'Account · Cloudflare One Networks → Edit (older dashboards: Cloudflare Tunnel → Edit)',
    'devices': 'Account · Zero Trust → Edit (turns on the Gateway proxy when it is off)',
}


def needed_permissions(cfg: Cluster) -> list[PermissionKey]:
    keys: list[PermissionKey] = ['tunnels', 'dns', 'access', 'idps', 'org']
    if config.private_network(cfg):
        keys += ['routes', 'devices']
    elif cfg['auth']['cloudflare']['require_warp']:
        keys.append('devices')
    return keys


def verify_token(api: Api, account: str) -> bool:
    """True when Cloudflare accepts the token (user tokens and account-owned tokens verify at different paths)."""
    for path in ('/user/tokens/verify', f'/accounts/{account}/tokens/verify'):
        try:
            if (api.call('GET', path) or {}).get('status') == 'active':
                return True
        except Failed:
            continue
    return False


def probe_token(cfg: Cluster, opener: Opener | None = None) -> list[tuple[PermissionKey, bool]] | None:
    """Read-only probes of what the token may do, for doctor: [(capability, ok)]; can't prove Edit."""
    api, account = api_for(cfg, opener), cfg['cloudflare']['account_id']
    if not verify_token(api, account):
        return None
    probes: list[tuple[PermissionKey, Callable[[], Reply]]] = []
    if cfg['auth']['ingress'] == 'cloudflared':
        probes.append(('tunnels', lambda: api.call('GET', f'/accounts/{account}/cfd_tunnel?per_page=1')))
        probes.append(('dns', lambda: _zone_records(api, cfg['cloudflare']['zone'])))
    if cfg['auth']['mode'] == 'cloudflare-access':
        probes.append(('access', lambda: api.call('GET', f'/accounts/{account}/access/apps')))
        probes.append(('idps', lambda: api.call('GET', f'/accounts/{account}/access/identity_providers')))
        if not cfg['auth']['cloudflare']['team']:
            probes.append(('org', lambda: api.call('GET', f'/accounts/{account}/access/organizations')))
        if config.private_network(cfg):
            probes.append(('routes', lambda: api.call('GET', f'/accounts/{account}/zerotrust/routes/hostname')))
        if config.private_network(cfg) or cfg['auth']['cloudflare']['require_warp']:
            probes.append(('devices', lambda: api.call('GET', f'/accounts/{account}/devices/settings')))
    out: list[tuple[PermissionKey, bool]] = []
    for name, probe in probes:
        try:
            probe()
            out.append((name, True))
        except Failed:
            out.append((name, False))
    return out


def client_only_checks(cfg: Cluster, opener: Opener | None = None) -> list[Fact]:
    """Read-only doctor facts for network = "private" or require_warp: [(id, ok, message, fix, severity)]."""
    api, account = api_for(cfg, opener), cfg['cloudflare']['account_id']
    s = Setup(cfg, api, Plan(True))
    out: list[Fact] = []
    private = config.private_network(cfg)
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
    org_sign_in: bool = False
    org: Json = {}
    try:
        org = api.call('GET', f'/accounts/{account}/access/organizations') or {}
        org_sign_in = bool(org.get('allow_authenticate_via_warp'))
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
    try:
        gaps = reauth_gaps(cfg, api, account, org)
        out.append(
            (
                'client-reauth',
                not gaps,
                'an expired client session can re-authenticate (Include-mode profiles list the team domain and the '
                'sign-in provider)'
                if not gaps
                else '; '.join(
                    f'the {n} device profile is in Include mode without {", ".join(m)}' for n, _, _, m in gaps
                )
                + ': an expired client asks to be connected and cannot be',
                'agentctl cloudflare setup',
                'error',
            )
        )
    except Failed:
        out.append(('client-reauth', True, "couldn't read the device profiles with this token", '', 'info'))
    apps = api.call('GET', f'/accounts/{account}/access/apps') or []
    app = next((a for a in apps if a.get('name') == s.name), None)
    out.append(
        (
            'client-sign-in',
            bool(app and app.get('allow_authenticate_via_warp')) or bool(org_sign_in),
            'devices on the client are signed in with their client session (no browser login; the T3 apps work)',
            'agentctl cloudflare setup; also check Zero Trust → Settings → WARP Client → Device enrollment: '
            '"WARP authentication identity" on',
            'error',
        )
    )
    if private:
        hosts = private_hosts(cfg)
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
        public: list[str] = []
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
    if config.private_https(cfg):
        out += https_checks(cfg, apps, app, s, bool(org_sign_in))
    if cfg['auth']['cloudflare']['require_warp']:
        policies = api.call('GET', f'/accounts/{account}/access/policies') or []
        people: Json = next((p for p in policies if p.get('name') == s.name), {})
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


def https_checks(cfg: Cluster, apps: list[Json], app: Json | None, s: Setup, org_sign_in: bool) -> list[Fact]:
    """Read-only private HTTPS checks: edge certificate, gate sign-in app and secrets, 443 on the people's app, redirect."""
    out: list[Fact] = []
    for host in signed_in_hosts(cfg):
        days, why = edge_certificate(host)
        out.append(
            (
                f'certificate-{host}',
                days is not None and days >= CERT_WARN_DAYS,
                f'the edge serves a trusted certificate for {host}'
                + (f' ({days} days left)' if days is not None else f': {why}'),
                "agentctl apply; if it stays, the edge's log names the Let's Encrypt problem (DNS → Edit on the zone "
                'for the token in acme_token_file)',
                'error' if days is None else 'warning',
            )
        )
    name, mine = s.named('sign-in'), gate_secret(cfg, 'client_id')
    sign_in = next((a for a in apps if a.get('name') == name), None)
    saas = (sign_in or {}).get('saas_app') or {}
    want = sorted(f'https://{h}{CALLBACK}' for h in signed_in_hosts(cfg))
    out.append(
        (
            'sign-in-app',
            bool(sign_in) and saas.get('client_id') == mine and sorted(saas.get('redirect_uris') or []) == want,
            f'the gate signs people in with {name} (Access for SaaS, OIDC), and holds its client',
            'agentctl cloudflare setup',
            'error',
        )
    )
    out.append(
        (
            'sign-in-client-session',
            bool((sign_in or {}).get('allow_authenticate_via_warp')) or org_sign_in,
            'the sign-in application accepts the Cloudflare One client session (no login prompt on enrolled devices)',
            'agentctl cloudflare setup sets it; without it people sign in once per session in the browser',
            'info',
        )
    )
    out.append(
        (
            'gate-secrets',
            all(gate_secret(cfg, k) for k in GATE_FILES),
            f'the gate has its client and session key ({gate_dir(cfg)})',
            'agentctl cloudflare setup (client), agentctl apply (session key)',
            'error',
        )
    )
    covered = {d.get('hostname') for d in (app or {}).get('destinations') or [] if d.get('port_range') == '443'}
    missing = [h for h in private_hosts(cfg) if h not in covered]
    out.append(
        (
            'https-port',
            not missing,
            'Access covers port 443 for every name'
            if not missing
            else f'Access does not cover port 443 for {", ".join(missing)} yet (plain HTTP works meanwhile)',
            'agentctl apply adds it once the certificate is in place',
            'warning',
        )
    )
    if not os.path.exists(f'{gate_dir(cfg)}/{LIVE}'):
        out.append(
            (
                'https-live',
                False,
                'plain HTTP is not redirected to HTTPS yet',
                'agentctl apply, once the two above pass',
                'info',
            )
        )
        return out
    for h in signed_in_hosts(cfg):
        ok, why = edge_redirect(h)
        out.append(
            (
                f'https-redirect-{h}',
                ok,
                f'http://{h} redirects to HTTPS' if ok else f'http://{h} does not redirect to HTTPS: {why}',
                'agentctl apply; if it persists, open an issue with this line',
                'error',
            )
        )
    return out


def enrollment_exposure(cfg: Cluster, api: Api, account: str, apps: list[Json], ours: str) -> list[Fact]:
    """Read-only warnings about what open client enrollment could expose elsewhere in the account."""
    out: list[Fact] = []
    domains = {d.lower() for d in cfg['auth']['allow_domains']}
    if domains:
        try:
            policies = {p.get('id'): p for p in api.call('GET', f'/accounts/{account}/access/policies') or []}
        except Failed:
            policies = {}
        open_apps = []
        for app in apps:
            if str(app.get('name', '')).startswith(ours) or app.get('type') == 'warp':
                continue
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
        if not any(_within(net, c) for c in covered):
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


Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def _within(net: Network, cover: Network) -> bool:
    """`net` lies inside `cover` (False across IP versions)."""
    if isinstance(net, ipaddress.IPv4Network) and isinstance(cover, ipaddress.IPv4Network):
        return net.subnet_of(cover)
    if isinstance(net, ipaddress.IPv6Network) and isinstance(cover, ipaddress.IPv6Network):
        return net.subnet_of(cover)
    return False


def _zone_records(api: Api, zone_name: str) -> Reply:
    zones = api.call('GET', f'/zones?name={zone_name}') or []
    if not zones:
        raise Failed(f'zone {zone_name} not visible to the token')
    return api.call('GET', f'/zones/{zones[0]["id"]}/dns_records?per_page=1')


def identity_providers(cfg: Cluster, opener: Opener | None = None) -> list[Json]:
    api = api_for(cfg, opener)
    return api.call('GET', f'/accounts/{cfg["cloudflare"]["account_id"]}/access/identity_providers') or []
