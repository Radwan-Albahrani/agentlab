"""cluster.toml -> the resolved cluster (the dict written to <data>/rendered/cluster.json). Validation is strict and
names the exact key: a typo that silently fell back to a default could expose an agent or size a disk wrong."""

import ipaddress
import json
import os
import re
import tomllib

from .util import Failed, gb, load_json, size_bytes, warn

DEFAULT_PATH = os.environ.get('AGENTLAB_CONFIG', '/etc/agentlab/cluster.toml')
ID = re.compile(r'^[a-z][a-z0-9-]{0,30}[a-z0-9]$|^[a-z]$')
EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
DOMAIN = re.compile(r'^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$')
TIME = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
RESERVED = {'edge', 'gate', 'hub', 'coolify', 'core', 'tinyauth'}  # names the cluster itself uses
SUBNET = '10.207.{n}.0/24'  # agent n's network; 10.207.0.0/24 is the edge's
TINYAUTH_IMAGE = 'ghcr.io/tinyauthapp/tinyauth:v5.1.3'  # >= 5.1.2 fixes CVE-2026-77560, 5.1.3 GHSA-r27r-rr9v-vv37

# Each sign-in mode, its default ingress and the ingresses it can work with.
MODES = {
    'cloudflare-access': ('cloudflared', {'cloudflared'}),
    'tailscale': ('tailscale', {'tailscale'}),
    'tinyauth': ('public', {'public', 'cloudflared'}),
    'none': ('loopback', {'loopback'}),
}

SCHEMA = {  # section -> {key: default}; None = required
    'cluster': {
        'name': None,
        'domain': None,
        'hub_domain': '',
        'coolify_domain': '',
        'pair_domain': '',
        'timezone': 'UTC',
        'data': '/srv/agentlab',
        'deploy': 'compose',
        'isolation': 'sysbox',
        'publish_address': '127.0.0.1',
    },
    'hub': {
        'publish': 0,
        'extra_stacks': [],
        'bark_url': '',
        'bark_public': '',
        'extra_secrets': '',  # a host folder of other secrets to show (admins only) on the Secrets screen
        'extra_secrets_map': '',  # its secrets-map (same format as hub/secrets-map.json), optional
        'extra_secrets_label': 'Other secrets',
    },
    'auth': {
        'mode': 'cloudflare-access',
        'ingress': '',
        'admins': None,
        'allow_domains': [],
        'hub_port': 8443,
        'cloudflare': {},
        'tinyauth': {},
    },
    'auth.cloudflare': {'team': '', 'audience': '', 'login_method': ''},
    'auth.tinyauth': {
        'domain': '',
        'google_client_id_file': '',
        'google_client_secret_file': '',
        'image': TINYAUTH_IMAGE,
    },
    'defaults': {'memory': '12g', 'cpus': 4},
    'storage': {'mode': 'shared', 'pool_size': '', 'pool_image': '', 'person_size': '80G', 'person_sizes': {}},
    'limits': {'total_memory': '96g', 'throttle_io_psi_max': 25},
    'android': {'enabled': False, 'system_image': 'system-images;android-35;google_apis;x86_64'},
    'backups': {'enabled': True, 'keep_days': 14, 'time': '03:30'},
    'cloudflare': {'account_id': '', 'zone': '', 'api_token_file': ''},
    'coolify': {'url': 'http://127.0.0.1:8000', 'token_file': '', 'project': 'agentlab'},
    'images': {'registry': '', 'tag': 'latest'},
    # agentlab: the nightly `agentctl update`; agent_tools_hours: agents refresh T3/Claude/Codex themselves (0 = never);
    # a busy agent is waited for up to wait_hours, then on_busy decides: "defer" (next night) or "resume" (restart it
    # and tell each interrupted chat to carry on)
    'updates': {
        'agentlab': 'off',
        'time': '04:30',
        'branch': 'main',
        'agent_tools_hours': 6,
        'wait_hours': 4,
        'on_busy': 'defer',
    },
    'companion_policy': {'self_service': True, 'max_per_agent': 0},  # 0 = no cap
}
AGENT_KEYS = {'id', 'owner', 'memory', 'cpus', 'publish', 'hostname', 'image', 'color'}
# The hub's agent colours (hub/web/src/theme/hues.ts); unset = picked from the id.
COLORS = ('green', 'pink', 'violet', 'amber', 'sky', 'red', 'teal', 'indigo')
PUBLISHABLE = ('t3', 'accounts', 'browser', 'terminal', 'files')
COMPANION_KEYS = {'name', 'agent', 'kind', 'display_name'}
COMPANION_KINDS = {'slack'}
AGENT_COMPANION = re.compile(r'^[a-z0-9][a-z0-9-]{0,28}[a-z0-9]$')  # names agents pick: 2-30 characters
PROJECT = re.compile(r'^[a-z0-9][a-z0-9_-]*$')  # what Docker Compose accepts as a project name
PRIVATE = ('cloudflare', 'coolify', 'images', 'tinyauth', 'person_sizes', 'seed', 'bark')


def load(path=DEFAULT_PATH):
    try:
        with open(path, encoding='utf-8') as f:
            text = f.read()
    except FileNotFoundError:
        raise Failed(f'{path} not found: copy cluster.example.toml there and edit it') from None
    return loads(text, path)


def loads(text, where='cluster.toml'):
    """Resolve config text, keeping each agent's subnet from the last apply."""
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise Failed(f'{where}: {e}') from None
    data = str((raw.get('cluster') or {}).get('data') or SCHEMA['cluster']['data']).rstrip('/')
    return resolve(
        raw,
        previous_subnets(load_json(os.path.join(data, 'rendered', 'cluster.json'), {})),
        load_state(data),
    )


def load_state(data):
    """{companions: [...], seeded: [names]}; seeded remembers which cluster.toml entries were already taken over."""
    state = load_json(state_file(data), {})
    if isinstance(state, list):
        state = {'companions': state}
    return {'companions': list(state.get('companions') or []), 'seeded': list(state.get('seeded') or [])}


def state_file(data):
    """Companions the agents created themselves; cluster.toml stays the admin's."""
    return os.path.join(data, 'state', 'companions.json')


def previous_subnets(cluster_json):
    """{agent id: n} from the last cluster.json, so an agent keeps its subnet (and the firewall its address)."""
    out = {}
    for a in cluster_json.get('agents') or []:
        m = re.match(r'^10\.207\.(\d+)\.0/24$', str(a.get('subnet', '')))
        if m and a.get('id'):
            out[a['id']] = int(m.group(1))
    return out


def _section(given, name, problems):
    label = f'[{name}]'
    if not isinstance(given, dict):
        problems.append(f'{label} must be a table')
        given = {}
    out = {}
    for key, default in SCHEMA[name].items():
        if key in given:
            out[key] = given[key]
        elif default is None:
            problems.append(f'{label} {key} is required')
        else:
            out[key] = default
    problems += [f'{label} unknown key {k!r}' for k in given if k not in SCHEMA[name]]
    return out


def _size(value, where, problems):
    try:
        size_bytes(value)
    except ValueError as e:
        problems.append(f'{where}: {e}')
        return str(value)
    return str(value).lower().removesuffix('b')


def _cpus(value, where, problems):
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        problems.append(f'{where}: cpus must be a positive number')
        return 1
    return value


LABEL = re.compile(r'^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$')


def _hostname(value, where, problems, required=True, local=False):
    """A DNS name. `local`: also a single-label name (a LAN or MagicDNS short name) or an IP address, which is how
    tailscale and none setups reached on plain ports are usually addressed; Cloudflare and tinyauth need real DNS."""
    value = str(value or '').lower()
    if not value and not required:
        return value
    if DOMAIN.match(value) or (local and (LABEL.match(value) or _is_ip(value))):
        return value
    problems.append(f'{where} {value!r} is not a hostname' + (', a machine name or an IP address' if local else ''))
    return value


def _is_ip(value):
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def person(email):
    """An owner's storage name: their email as a slug (sara@example.com -> sara-example-com)."""
    return re.sub(r'[^a-z0-9]+', '-', email.lower()).strip('-')


def _storage(raw, problems):
    s = _section(raw.get('storage', {}), 'storage', problems)
    if s['mode'] not in ('shared', 'per-person'):
        problems.append('[storage] mode must be "shared" or "per-person"')
        s['mode'] = 'shared'
    if s['pool_size']:
        s['pool_size'] = _size(s['pool_size'], '[storage] pool_size', problems)
    s['person_size'] = _size(s['person_size'], '[storage] person_size', problems)
    if s['pool_image'] and not str(s['pool_image']).startswith('/'):
        problems.append('[storage] pool_image must be an absolute path')
    if not isinstance(s['person_sizes'], dict):
        problems.append('[storage] person_sizes must be a table of "email" = "size"')
        s['person_sizes'] = {}
    s['person_sizes'] = {
        str(k).lower(): _size(v, f'[storage] person_sizes {k}', problems) for k, v in s['person_sizes'].items()
    }
    return s


def _port(value, where, problems):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        problems.append(f'{where}: {value!r} is not a port number')
        return 0
    return value


def _publish(value, where, problems):
    """{tool: host port} an agent's tools are also published on (one-person setups that predate the edge)."""
    if not isinstance(value, dict):
        problems.append(f'{where} must be a table like {{ t3 = 7101 }}')
        return {}
    problems += [f'{where}: unknown tool {k!r} (use {", ".join(PUBLISHABLE)})' for k in value if k not in PUBLISHABLE]
    return {k: _port(v, f'{where}.{k}', problems) for k, v in value.items() if k in PUBLISHABLE}


def from_state(entries, agent_ids):
    """The valid companions in the state file. One whose agent is gone (or that is otherwise broken) is left out with
    a warning, never an error: what an agent did must not be able to break the admin's apply."""
    out, taken = [], set()
    for e in entries:
        name = str(e.get('name', '')) if isinstance(e, dict) else ''
        ok = (
            AGENT_COMPANION.match(name)
            and name not in RESERVED
            and name not in taken
            and e.get('agent') in agent_ids
            and e.get('kind', 'slack') in COMPANION_KINDS
        )
        if not ok:
            warn(f'companion {name or e!r} in the state file skipped (invalid, a duplicate, or its agent is gone)')
            continue
        taken.add(name)
        out.append(
            {
                'name': name,
                'display_name': str(e.get('display_name') or name)[:60],
                'agent': e['agent'],
                'kind': e.get('kind', 'slack'),
            }
        )
    return out


def _subnets(ids, previous):
    """A stable /24 per agent: kept from the last apply, new agents take the lowest free number."""
    taken = {previous[i] for i in ids if i in previous}
    out, free = {}, (n for n in range(1, 255) if n not in taken)
    for i in ids:
        out[i] = previous[i] if i in previous else next(free)
    return out


def _auth(raw, problems):
    a = _section(raw.get('auth', {}), 'auth', problems)
    cf = _section(a.pop('cloudflare') or {}, 'auth.cloudflare', problems)
    ta = _section(a.pop('tinyauth') or {}, 'auth.tinyauth', problems)
    mode = a['mode']
    if mode not in MODES:
        problems.append(f'[auth] mode must be one of {", ".join(MODES)}')
        mode = 'none'
    default, allowed = MODES[mode]
    a['ingress'] = a['ingress'] or default
    if a['ingress'] not in allowed:
        problems.append(f'[auth] ingress {a["ingress"]!r} does not work with mode {mode!r} (use {sorted(allowed)})')
    admins = a.get('admins')
    if not isinstance(admins, list) or not admins or not all(isinstance(x, str) and EMAIL.match(x) for x in admins):
        problems.append('[auth] admins must be a non-empty list of email addresses')
        admins = []
    a['admins'] = [x.lower() for x in admins]
    domains = a['allow_domains']
    if not isinstance(domains, list) or not all(isinstance(d, str) and DOMAIN.match(d.lower()) for d in domains):
        problems.append('[auth] allow_domains must be a list of email domains, e.g. ["example.com"]')
        domains = []
    if domains and mode not in ('cloudflare-access', 'tinyauth'):
        problems.append(
            '[auth] allow_domains works with cloudflare-access and tinyauth (Tailscale: use the tailnet ACL)'
        )
    a['allow_domains'] = sorted({d.lower() for d in domains})
    # team may stay empty: `agentctl cloudflare setup` reads it from the account and writes it here
    if cf['team'] and not re.match(r'^[a-z0-9][a-z0-9-]*$', str(cf['team'])):
        problems.append('[auth.cloudflare] team must be the <team> of <team>.cloudflareaccess.com')
    if mode == 'tinyauth':
        ta['domain'] = _hostname(ta['domain'], '[auth.tinyauth] domain', problems)
        for key in ('google_client_id_file', 'google_client_secret_file'):
            if ta[key] and not str(ta[key]).startswith('/'):
                problems.append(f'[auth.tinyauth] {key} must be an absolute path')
    port = a['hub_port']
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535 or port == 443:
        problems.append('[auth] hub_port must be a port number other than 443')
    return a, cf, ta


def resolve(raw, previous=None, state=None):
    """The validated, defaulted config in the shape of docs/architecture.md (cluster.json) plus agentctl's own keys.
    Raises Failed listing every problem at once."""
    problems = []
    unknown = set(raw) - {
        'cluster',
        'hub',
        'auth',
        'defaults',
        'storage',
        'limits',
        'android',
        'backups',
        'cloudflare',
        'coolify',
        'images',
        'updates',
        'companion_policy',
        'agents',
        'companions',
    }
    problems += [f'unknown section [{k}]' for k in sorted(unknown)]
    c = _section(raw.get('cluster', {}), 'cluster', problems)
    auth, auth_cf, auth_ta = _auth(raw, problems)
    defaults = _section(raw.get('defaults', {}), 'defaults', problems)
    storage = _storage(raw, problems)
    hub = _section(raw.get('hub', {}), 'hub', problems)
    extra = hub['extra_stacks']
    if not isinstance(extra, list) or not all(isinstance(x, str) and PROJECT.match(x) for x in extra):
        problems.append('[hub] extra_stacks must be a list of Compose project names (lowercase, digits, - and _)')
        hub['extra_stacks'] = []
    for key in ('extra_secrets', 'extra_secrets_map'):
        if hub[key] and not str(hub[key]).startswith('/'):
            problems.append(f'[hub] {key} must be an absolute path on this host')
    if hub['extra_secrets_map'] and not hub['extra_secrets']:
        problems.append('[hub] extra_secrets_map needs extra_secrets (the folder it describes)')
    for key in ('bark_url', 'bark_public'):
        if hub[key] and not re.match(r'^https?://[^\s/]+', str(hub[key])):
            problems.append(f'[hub] {key} must be an http(s) address, e.g. "http://host.docker.internal:7192"')
    limits = _section(raw.get('limits', {}), 'limits', problems)
    android = _section(raw.get('android', {}), 'android', problems)
    backups = _section(raw.get('backups', {}), 'backups', problems)
    cloudflare = _section(raw.get('cloudflare', {}), 'cloudflare', problems)
    coolify = _section(raw.get('coolify', {}), 'coolify', problems)
    images = _section(raw.get('images', {}), 'images', problems)
    updates = _section(raw.get('updates', {}), 'updates', problems)
    if updates['agentlab'] not in ('off', 'daily'):
        problems.append('[updates] agentlab must be "off" or "daily"')
    if not TIME.match(str(updates['time'])):
        problems.append('[updates] time must be HH:MM')
    if updates['on_busy'] not in ('defer', 'resume'):
        problems.append('[updates] on_busy must be "defer" or "resume"')
    for key in ('agent_tools_hours', 'wait_hours'):
        v = updates[key]
        if isinstance(v, bool) or not isinstance(v, int | float) or v < 0:
            problems.append(f'[updates] {key} must be a number of hours (0 or more)')
    if not str(updates['branch']).strip():
        problems.append('[updates] branch must name a branch')
    policy = _section(raw.get('companion_policy', {}), 'companion_policy', problems)
    if not isinstance(policy['self_service'], bool):
        problems.append('[companion_policy] self_service must be true or false')
    if (
        isinstance(policy['max_per_agent'], bool)
        or not isinstance(policy['max_per_agent'], int)
        or policy['max_per_agent'] < 0
    ):
        problems.append('[companion_policy] max_per_agent must be a whole number')
    images['registry'] = str(images['registry']).rstrip('/')
    mode = auth['mode']

    local = mode in ('tailscale', 'none')  # reached inside a tailnet or LAN, often by a bare name or an IP
    c['domain'] = _hostname(c.get('domain'), '[cluster] domain', problems, local=local)
    if mode == 'tailscale':
        c['hub_domain'] = _hostname(c['hub_domain'] or c['domain'], '[cluster] hub_domain', problems, local=True)
    else:
        c['hub_domain'] = _hostname(c['hub_domain'], '[cluster] hub_domain', problems, local=local)
    c['coolify_domain'] = _hostname(c['coolify_domain'], '[cluster] coolify_domain', problems, required=False)
    hosts = [c['domain'], c['coolify_domain'], auth_ta['domain'] if mode == 'tinyauth' else '']
    if mode != 'tailscale':  # tailscale serves the hub on the same name, on its own port
        hosts.append(c['hub_domain'])
    hosts = [h for h in hosts if h]
    if len(set(hosts)) != len(hosts):
        problems.append('domain, hub_domain, coolify_domain and the tinyauth domain must all differ')
    pair = str(c['pair_domain'] or '').lower()
    if pair and ('{id}' not in pair or not DOMAIN.match(pair.replace('{id}', 'x'))):
        problems.append('[cluster] pair_domain must be a hostname pattern with {id}, e.g. "{id}-t3.example.com"')
    c['pair_domain'] = pair if mode in ('cloudflare-access', 'tinyauth') else ''
    if c.get('deploy') not in ('coolify', 'compose'):
        problems.append('[cluster] deploy must be "coolify" or "compose"')
    if c.get('isolation') not in ('sysbox', 'unconfined'):
        problems.append('[cluster] isolation must be "sysbox" or "unconfined"')
    if not str(c.get('data', '')).startswith('/'):
        problems.append('[cluster] data must be an absolute path')
    c['data'] = str(c.get('data', '')).rstrip('/') or '/'

    default_memory = _size(defaults['memory'], '[defaults] memory', problems)
    default_cpus = _cpus(defaults['cpus'], '[defaults] cpus', problems)
    total = _size(limits['total_memory'], '[limits] total_memory', problems)

    agents, seen = [], []
    raw_agents = raw.get('agents', [])
    if not isinstance(raw_agents, list) or not raw_agents:
        problems.append('at least one [[agents]] entry is required')
        raw_agents = []
    for n, a in enumerate(raw_agents, 1):
        where = f'[[agents]] #{n}'
        if not isinstance(a, dict):
            problems.append(f'{where} must be a table')
            continue
        problems += [f'{where}: unknown key {k!r}' for k in a if k not in AGENT_KEYS]
        aid, owner = str(a.get('id', '')), str(a.get('owner', '')).lower()
        if not ID.match(aid) or aid in RESERVED:
            problems.append(
                f'{where}: id {aid!r} must be lowercase letters, digits and dashes (not {sorted(RESERVED)})'
            )
        if aid in seen:
            problems.append(f'{where}: id {aid!r} is used twice')
        seen.append(aid)
        if not EMAIL.match(owner):
            problems.append(f'{where} ({aid}): owner must be an email address')
        pair_host = c['pair_domain'].replace('{id}', aid) if c['pair_domain'] else ''
        color = str(a.get('color') or '')
        if color and color not in COLORS:
            problems.append(f'{where} ({aid}): color {color!r} must be one of {", ".join(COLORS)}')
        if storage['mode'] == 'per-person':
            unit = f'{c["data"]}/people/{person(owner)}'
            path = f'{unit}/{aid}'
        else:
            unit = f'{c["data"]}/agents' if storage['pool_size'] else ''
            path = f'{c["data"]}/agents/{aid}'
        agents.append(
            {
                'id': aid,
                'owner': owner,
                'memory': _size(a.get('memory', default_memory), f'{where} memory', problems),
                'cpus': _cpus(a.get('cpus', default_cpus), f'{where} cpus', problems),
                'upstream': f'http://agent-{aid}',
                'hostname': str(a.get('hostname') or f'agent-{aid}'),
                'image': str(a.get('image') or ''),
                'publish': _publish(a.get('publish', {}), f'{where} publish', problems),
                'path': path,
                'storage_unit': unit,  # the mounted image this agent's files live on; '' = the host's filesystem
                'subnet': '',
                'pair_host': pair_host,
                'color': color,
            }
        )
    published = [p for a in agents for p in a['publish'].values()] + ([hub['publish']] if hub['publish'] else [])
    if published:
        _port(hub['publish'] or 1, '[hub] publish', problems)
        owners = {a['owner'] for a in agents}
        if mode not in ('tailscale', 'none') or len(owners) > 1:
            problems.append(
                'published ports (agents.publish, hub.publish) bypass the gate: they are allowed only '
                'with auth.mode "tailscale" or "none" and a single owner'
            )
        if len(published) != len(set(published)):
            problems.append('a published port is used twice')
    slugs = {}
    for o in {a['owner'] for a in agents if EMAIL.match(a['owner'])}:
        slugs.setdefault(person(o), []).append(o)
    problems += [
        f'owners {" and ".join(sorted(v))} map to the same storage name; rename one'
        for v in slugs.values()
        if len(v) > 1
    ]
    for email in storage['person_sizes']:
        if email not in {a['owner'] for a in agents}:
            problems.append(f'[storage] person_sizes: {email} owns no agent')
    if len(agents) > 254:
        problems.append('at most 254 agents (one /24 each in 10.207.0.0/16)')
    else:
        subnets = _subnets([a['id'] for a in agents], previous or {})
        for a in agents:
            a['subnet'] = SUBNET.format(n=subnets[a['id']])
    pair_hosts = [a['pair_host'] for a in agents if a['pair_host']]
    if set(pair_hosts) & set(hosts):
        problems.append('a pair host collides with domain, hub_domain or coolify_domain')

    companions = []
    for n, comp in enumerate(raw.get('companions', []) or [], 1):
        where = f'[[companions]] #{n}'
        if not isinstance(comp, dict):
            problems.append(f'{where} must be a table')
            continue
        problems += [f'{where}: unknown key {k!r}' for k in comp if k not in COMPANION_KEYS]
        name = str(comp.get('name', ''))
        if not AGENT_COMPANION.match(name) or name in RESERVED:
            problems.append(f'{where}: name {name!r} must be 2-30 lowercase letters, digits and dashes')
        if comp.get('agent') not in seen:
            problems.append(f'{where} ({name}): agent {comp.get("agent")!r} is not an agent id')
        if comp.get('kind', 'slack') not in COMPANION_KINDS:
            problems.append(f'{where} ({name}): kind must be one of {sorted(COMPANION_KINDS)}')
        companions.append(
            {
                'name': name,
                'display_name': str(comp.get('display_name') or name),
                'agent': comp.get('agent'),
                'kind': comp.get('kind', 'slack'),
            }
        )
    names = [x['name'] for x in companions]
    problems += [f'companion {x!r} is defined twice' for x in sorted({x for x in names if names.count(x) > 1})]
    # The state file is the truth (agents create, change and remove their companions); a [[companions]] entry only
    # seeds it once, so one its agent removed stays removed.
    state = state or {'companions': [], 'seeded': []}
    live = from_state(state['companions'], seen)
    have, seeded = {c['name'] for c in live}, set(state['seeded'])
    seeds = [c for c in companions if c['name'] not in seeded and c['name'] not in have]
    companions = live + seeds

    if not isinstance(backups['enabled'], bool):
        problems.append('[backups] enabled must be true or false')
    if not TIME.match(str(backups['time'])):
        problems.append('[backups] time must be HH:MM')
    if not isinstance(backups['keep_days'], int) or backups['keep_days'] < 1:
        problems.append('[backups] keep_days must be a whole number of days, at least 1')
    psi = limits['throttle_io_psi_max']
    if not isinstance(psi, int | float) or not 0 < psi <= 100:
        problems.append('[limits] throttle_io_psi_max must be a percentage')
    # Secrets live at fixed places under <data>/secrets unless the config points elsewhere (`agentctl secret set`
    # writes them there).
    secrets = f'{c["data"]}/secrets'
    cloudflare['api_token_file'] = str(cloudflare['api_token_file'] or f'{secrets}/cloudflare-api.token')
    coolify['token_file'] = str(coolify['token_file'] or f'{secrets}/coolify.token')
    auth_ta['google_client_id_file'] = str(auth_ta['google_client_id_file'] or f'{secrets}/tinyauth-google-id')
    auth_ta['google_client_secret_file'] = str(
        auth_ta['google_client_secret_file'] or f'{secrets}/tinyauth-google-secret'
    )
    if problems:
        raise Failed('cluster.toml has problems:\n  ' + '\n  '.join(problems))

    return {
        'name': c['name'],
        'domain': c['domain'],
        'timezone': c['timezone'],
        'data': c['data'],
        'deploy': c['deploy'],
        'isolation': c['isolation'],
        'auth': {
            'mode': mode,
            'ingress': auth['ingress'],
            'admins': auth['admins'],
            'allow_domains': auth['allow_domains'],
            'cloudflare': {'team': auth_cf['team'], 'audience': auth_cf['audience']},
            'tinyauth': {'domain': auth_ta['domain'] if mode == 'tinyauth' else ''},
            'hub_port': auth['hub_port'],
        },
        'hub_domain': c['hub_domain'],
        'publish_address': str(c['publish_address']),
        'hub': {
            'publish': hub['publish'],
            'extra_stacks': hub['extra_stacks'],
            'extra_secrets': {
                'folder': str(hub['extra_secrets']).rstrip('/'),
                'map': str(hub['extra_secrets_map']),
                'label': str(hub['extra_secrets_label']) or 'Other secrets',
            },
        },
        'bark': {'url': str(hub['bark_url']).rstrip('/'), 'public': str(hub['bark_public']).rstrip('/')},
        'coolify_domain': c['coolify_domain'],
        'pair_domain': c['pair_domain'],
        'agents': agents,
        'storage': {
            'mode': storage['mode'],
            'pool_size': storage['pool_size'],
            'pool_image': storage['pool_image'] or f'{c["data"]}/disks/pool.img',
            'person_size': storage['person_size'],
        },
        'limits': {
            'total_memory': total,
            'throttle': {'agent_gb': gb(default_memory), 'pool_gb': gb(total), 'io_psi_max': psi},
        },
        'android': {'enabled': bool(android['enabled']), 'system_image': android['system_image']},
        'backups': {'enabled': backups['enabled'], 'keep_days': backups['keep_days'], 'time': backups['time']},
        'companions': companions,
        'seed': [c['name'] for c in seeds],  # cluster.toml entries apply records in the state file
        'companion_policy': policy,
        'updates': updates,
        # Below: only agentctl's (file paths, never secrets themselves); left out of cluster.json.
        'cloudflare': {**cloudflare, 'login_method': str(auth_cf['login_method'])},
        'coolify': coolify,
        'images': images,
        'tinyauth': auth_ta,
        'person_sizes': storage['person_sizes'],
    }


def public(cfg):
    """cluster.json: the resolved config minus agentctl's own settings, read by the gate, hub, edge and host."""
    return {k: v for k, v in cfg.items() if k not in PRIVATE}


def to_json(cfg):
    return json.dumps(public(cfg), indent=2) + '\n'


def ports_only(cfg):
    """Whether people reach everything on published ports (the hub and every agent's T3): a one-person setup that
    keeps its own network as the way in, so `tailscale serve`, tailnet HTTPS and the edge's ingress aren't used."""
    agents = cfg['agents']
    return bool(cfg['hub']['publish']) and bool(agents) and all('t3' in a['publish'] for a in agents)


def agent(cfg, agent_id):
    found = next((a for a in cfg['agents'] if a['id'] == agent_id), None)
    if not found:
        raise Failed(f'no agent {agent_id!r} in the config (agentctl agent list)')
    return found


def agent_ip(a):
    return a['subnet'].replace('.0/24', '.2')


def gateway(subnet):
    return subnet.replace('.0/24', '.1')
