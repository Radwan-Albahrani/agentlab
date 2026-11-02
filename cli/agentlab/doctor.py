"""`agentctl doctor`: every check the cluster depends on, each with the exact fix (a command, or the manual step).
Errors exit 1; warnings are things that work but shouldn't stay that way."""

import json
import os
import platform
import re
import shutil
import socket
import urllib.request

from . import cloudflare, config, coolify, deploy, disks, render
from .util import is_root, run, size_bytes


class Checks:
    def __init__(self):
        self.items = []

    def add(self, cid, ok, message, fix='', severity='error'):
        self.items.append(
            {
                'id': cid,
                'ok': bool(ok),
                'severity': 'ok' if ok else severity,
                'message': message,
                'fix': '' if ok else fix,
            }
        )

    def sudo(self, cid, what):
        """A check this user may not see (root-only files, nft, the Docker socket): a warning, not a failure."""
        self.add(cid, False, f'not checked without root: {what}', 'run `sudo agentctl doctor` to include it', 'warning')


def _private(path):
    """Whether a root-only file exists, or None when this user can't look (a 0700 secrets folder)."""
    if not path:
        return False
    if is_root() or os.access(os.path.dirname(path) or '/', os.X_OK):
        return os.path.isfile(path)
    return None


def _kernel():
    m = re.match(r'(\d+)\.(\d+)', platform.release())
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def _wsl():
    try:
        with open('/proc/version') as f:
            return 'microsoft' in f.read().lower()
    except OSError:
        return False


def _os_name():
    try:
        with open('/etc/os-release') as f:
            info = dict(line.rstrip().split('=', 1) for line in f if '=' in line)
        return info.get('PRETTY_NAME', '').strip('"'), info.get('ID', ''), info.get('VERSION_ID', '').strip('"')
    except OSError:
        return 'unknown', '', ''


def _mem_total():
    try:
        with open('/proc/meminfo') as f:
            return int(next(line for line in f if line.startswith('MemTotal')).split()[1]) * 1024
    except (OSError, StopIteration):
        return 0


def _active(unit):
    return run(['systemctl', 'is-active', unit], check=False)[1] == 'active'


def _listening(port, host='127.0.0.1'):
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def host(cfg, c):
    name, distro, version = _os_name()
    c.add(
        'os',
        (distro == 'ubuntu' and version in ('22.04', '24.04')) or (distro == 'debian' and version == '12'),
        f'OS: {name}',
        'agentlab is tested on Ubuntu 24.04 (22.04 and Debian 12 should work)',
        'warning',
    )
    c.add(
        'kernel',
        _kernel() >= (5, 19) or cfg['isolation'] != 'sysbox',
        f'kernel {platform.release()}',
        'Sysbox needs Linux 5.19+ for ID-mapped mounts: upgrade the kernel (Ubuntu 24.04 ships 6.8)',
    )
    if cfg['isolation'] == 'sysbox' and _wsl():
        c.add(
            'wsl-sysbox',
            False,
            'isolation = "sysbox" on WSL',
            'Sysbox cannot run on WSL: set isolation = "unconfined" (one person only) or use a Linux server',
        )
    owners = {a['owner'] for a in cfg['agents']}
    c.add(
        'isolation',
        cfg['isolation'] == 'sysbox' or len(owners) <= 1,
        f'isolation = {cfg["isolation"]} with {len(owners)} people',
        'unconfined containers are not a boundary between people: agentctl install (Sysbox), then set '
        'isolation = "sysbox"',
        'warning',
    )
    total = _mem_total()
    want = size_bytes(cfg['limits']['total_memory'])
    c.add(
        'memory',
        total and want <= total * 0.85,
        f'limits.total_memory {cfg["limits"]["total_memory"]} of {total / 2**30:.0f} GiB RAM',
        'leave at least 15% of RAM to the host: lower [limits] total_memory',
        'error' if want > total else 'warning',
    )
    storage(cfg, c)


def storage(cfg, c):
    root = cfg['data'] if os.path.isdir(cfg['data']) else '/'
    fs = disks.usage(root)
    units = disks.units(cfg)
    if not units:
        c.add(
            'storage',
            True,
            f'shared folder {cfg["data"]}/agents on the host disk: '
            f'{fs["used"] / 2**30:.0f} of {fs["size"] / 2**30:.0f} GiB used',
        )
        return
    # Images are sparse: what they may still grow by must fit in what the host has free.
    allocated = sum(os.stat(u['image']).st_blocks * 512 for u in units if os.path.exists(u['image']))
    promised = sum(size_bytes(u['size']) for u in units)
    c.add(
        'storage-budget',
        promised - allocated <= fs['avail'],
        f'storage images may grow by {(promised - allocated) / 2**30:.0f} GiB; '
        f'{fs["avail"] / 2**30:.0f} GiB free on the host disk',
        'lower [storage] pool_size / person_size, or free space on the host',
        'warning',
    )
    for u in units:
        c.add(
            f'storage-{u["name"]}',
            os.path.ismount(u['mount']),
            f'{u["name"]} disk mounted at {u["mount"]}',
            'agentctl apply',
        )


def docker(cfg, c):
    has = shutil.which('docker') is not None
    rc, version = run(['docker', 'version', '--format', '{{.Server.Version}}'], check=False) if has else (1, '')
    if rc and has and not is_root() and 'permission denied' in version.lower():
        c.sudo('docker', 'Docker and everything running in it (this user cannot reach the Docker socket)')
        return False
    c.add('docker', rc == 0, f'Docker {version}' if rc == 0 else 'Docker not running', 'agentctl install')
    if rc:
        return False
    c.add(
        'compose',
        run(['docker', 'compose', 'version'], check=False)[0] == 0,
        'docker compose plugin',
        'agentctl install',
    )
    if cfg['isolation'] == 'sysbox':
        runtimes = run(['docker', 'info', '--format', '{{json .Runtimes}}'], check=False)[1]
        c.add(
            'sysbox',
            'sysbox-runc' in runtimes and _active('sysbox'),
            'Sysbox runtime',
            'agentctl install (installs Sysbox CE and registers sysbox-runc)',
        )
    return True


def android(cfg, c):
    if not cfg['android']['enabled']:
        return
    # Root (and the agents, through the udev rule) is what has to use it, not whoever runs doctor.
    kvm = os.path.exists('/dev/kvm') and (not is_root() or os.access('/dev/kvm', os.R_OK | os.W_OK))
    c.add(
        'kvm',
        kvm,
        '/dev/kvm usable',
        'enable virtualization (VT-x/AMD-V) in the BIOS, then agentctl install; or set [android] enabled = false',
    )
    sdk = f'{cfg["data"]}/shared/android-sdk'
    c.add('android-sdk', os.path.exists(f'{sdk}/emulator/emulator'), f'Android SDK in {sdk}', 'agentctl install')


def _domain_levels(cfg, c):
    zone = cfg['cloudflare']['zone']
    if not zone:
        return
    for host_name in render.public_hosts(cfg):
        one_below = host_name.endswith('.' + zone) and '.' not in host_name[: -len(zone) - 1]
        c.add(
            f'level-{host_name}',
            one_below,
            f'{host_name} is one label below {zone}',
            f"Cloudflare's free certificate covers only <name>.{zone}: use a name like agents.{zone}",
            'warning',
        )


def access(cfg, c):
    mode, ingress = cfg['auth']['mode'], cfg['auth']['ingress']
    if mode == 'none' and not config.ports_only(cfg):
        c.add(
            'auth',
            False,
            'auth.mode = "none": only this machine can reach the agents, and everyone is admin',
            'for real use set [auth] mode to cloudflare-access, tailscale or tinyauth',
            'warning',
        )
    if ingress == 'cloudflared':
        _cloudflared(cfg, c)
    token_file = cfg['cloudflare'].get('api_token_file')
    if (ingress == 'cloudflared' or mode == 'cloudflare-access') and token_file and not os.access(token_file, os.R_OK):
        if not is_root() and _private(token_file) is not False:
            c.sudo('cloudflare-token', f'the Cloudflare API token in {token_file} and what it can reach')
    elif (ingress == 'cloudflared' or mode == 'cloudflare-access') and cloudflare.configured(cfg):
        _cloudflare_token(cfg, c)
    if mode == 'cloudflare-access':
        _cloudflare_access(cfg, c)
    if mode == 'tailscale':
        _tailscale(cfg, c)
    if mode == 'tinyauth':
        _tinyauth(cfg, c)
    if ingress == 'public':
        for port in (80, 443):
            c.add(
                f'public-{port}',
                _listening(port),
                f'edge listening on :{port}',
                f"agentctl apply; then open port {port} in the server's and the network's firewall",
            )
    published = [p for a in cfg['agents'] for p in a['publish'].values()] + [cfg['hub']['publish'] or None]
    if any(published):
        c.add(
            'published',
            False,
            f'ports published on {cfg["publish_address"]}: '
            f'{", ".join(str(p) for p in published if p)} (they skip the edge and the gate)',
            'fine for a one-person setup behind your own firewall; remove [agents.publish] / [hub] publish otherwise',
            'warning',
        )


def _cloudflared(cfg, c):
    token = f'{cfg["data"]}/secrets/cloudflare-tunnel.token'
    if _private(token) is None:
        c.sudo('tunnel-token', f'tunnel token in {token}')
    else:
        c.add('tunnel-token', _private(token), f'tunnel token in {token}', 'agentctl cloudflare setup')
    c.add(
        'cloudflared',
        bool(shutil.which('cloudflared')) and _active('cloudflared'),
        'cloudflared running',
        'agentctl install (after agentctl cloudflare setup wrote the token)',
    )
    _domain_levels(cfg, c)


def _cloudflare_token(cfg, c):
    """The API token is valid and reaches every area `cloudflare setup` touches (read-only probes)."""
    try:
        probes = cloudflare.probe_token(cfg)
    except Exception as e:  # reported as a check, not a crash
        c.add('cloudflare-token', False, f'Cloudflare API: {e}', 'agentctl secret set cloudflare-api (a new token)')
        return
    if probes is None:
        c.add(
            'cloudflare-token',
            False,
            'Cloudflare API token is valid',
            'the token was refused (expired, revoked or mistyped): create a new one in My Profile → API Tokens, '
            'then agentctl secret set cloudflare-api',
        )
        return
    c.add('cloudflare-token', True, 'Cloudflare API token is valid')
    for name, ok in probes:
        c.add(
            f'cloudflare-token-{name}',
            ok,
            f'token reaches {name}' if ok else f'token lacks {cloudflare.PERMISSIONS[name]}',
            f'edit the token (My Profile → API Tokens) and add: {cloudflare.PERMISSIONS[name]}',
        )


def _cloudflare_access(cfg, c):
    c.add(
        'audience',
        bool(cfg['auth']['cloudflare']['team'] and cfg['auth']['cloudflare']['audience']),
        'Cloudflare Access application known (team and audience)',
        'agentctl cloudflare setup (finds the team and creates the application); until then the gate refuses everyone',
    )
    token_file = cfg['cloudflare'].get('api_token_file')
    if not is_root() and token_file and not os.access(token_file, os.R_OK) and _private(token_file) is not False:
        c.sudo('cloudflare-api', 'the Access login methods (the API token is root-only)')
        return
    if not cloudflare.configured(cfg):
        c.add(
            'cloudflare-api',
            False,
            'Cloudflare API token saved',
            'create a token (My Profile → API Tokens) and save it: agentctl secret set cloudflare-api',
            'warning',
        )
        return
    try:
        idps = cloudflare.identity_providers(cfg)
    except Exception as e:  # reported as a check, not a crash
        c.add('cloudflare-api', False, f'Cloudflare API: {e}', 'agentctl secret set cloudflare-api (a new token)')
        return
    wanted = cfg['cloudflare'].get('login_method')
    if wanted:
        names = [str(i.get('name', '')) for i in idps]
        c.add(
            'login-method',
            wanted.strip().lower() in {n.strip().lower() for n in names},
            f'login method {wanted!r} exists in Cloudflare Zero Trust',
            f'set [auth.cloudflare] login_method to one of: {", ".join(names) or "(none yet: add one in Zero Trust)"}',
        )
        return
    names = ', '.join(str(i.get('name', '')) for i in idps)
    c.add(
        'login-methods',
        True,  # information only: any method works, the one-time PIN by email needs no setup
        f'Zero Trust login methods offered: {names or "none listed (the one-time PIN by email still works)"}'
        + ('; [auth.cloudflare] login_method can pin people to one' if names else ''),
    )


WINDOWS_TAILSCALE = '/mnt/c/Program Files/Tailscale/tailscale.exe'


def tailscale_cli():
    """The tailscale command for this host: Linux's own, or on WSL the Windows one (Tailscale usually runs on
    Windows there; with mirrored networking its `tailscale serve` reaches the edge on WSL's loopback)."""
    if shutil.which('tailscale'):
        return 'tailscale'
    if _wsl() and os.access(WINDOWS_TAILSCALE, os.X_OK):
        return WINDOWS_TAILSCALE
    return None


def _tailscale(cfg, c):
    cli = tailscale_cli()
    rc, out = run([cli, 'status', '--json'], check=False) if cli else (1, '')
    try:
        status = json.loads(out) if rc == 0 else {}
    except ValueError:
        status = {}
    state = status.get('BackendState', '')
    c.add(
        'tailscale',
        state == 'Running',
        f'Tailscale {state or "not running"}' + (' (Windows)' if cli == WINDOWS_TAILSCALE else ''),
        'install Tailscale and run: sudo tailscale up (on WSL: Tailscale for Windows, signed in)',
    )
    if config.ports_only(cfg):
        c.add(
            'tailscale-ports',
            True,
            'everything is on published ports over your tailnet: tailscale serve and tailnet HTTPS are not used',
        )
        c.add(
            'tailscale-acl',
            False,
            "who may reach the published ports is decided by your tailnet ACL and this host's firewall",
            'manual: allow only your own devices to reach this node on the published ports',
            'warning',
        )
        return
    if state == 'Running':
        c.add(
            'tailscale-https',
            bool(status.get('CertDomains')),
            'tailnet HTTPS certificates (tailscale serve needs them)',
            'manual: Tailscale admin console → DNS → enable MagicDNS and HTTPS Certificates',
        )
    serve = run([cli, 'serve', 'status', '--json'], check=False)[1] if cli else ''
    want = [f'127.0.0.1:{render.INGRESS_PORT}', f'127.0.0.1:{render.HUB_INGRESS_PORT}']
    c.add(
        'tailscale-serve',
        all(w in serve for w in want),
        'tailscale serve maps 443 and the hub port to the edge',
        'agentctl install (step tailscale)',
    )
    c.add(
        'tailscale-acl',
        False,
        'who may reach this machine is decided by your tailnet ACL',
        'manual: in the Tailscale admin console, allow exactly the agent owners and admins to reach this node on '
        f'443 and {cfg["auth"]["hub_port"]}',
        'warning',
    )


def _tinyauth(cfg, c):
    t = cfg['tinyauth']
    for key in ('google_client_id_file', 'google_client_secret_file'):
        if _private(t[key]) is None:
            c.sudo(f'tinyauth-{key}', f'tinyauth {key.replace("_", " ")}: {t[key]}')
            continue
        c.add(
            f'tinyauth-{key}',
            os.path.isfile(t[key]),
            f'tinyauth {key.replace("_", " ")}: {t[key]}',
            'create a Google OAuth client (redirect https://'
            f'{t["domain"]}/api/oauth/callback/google), then agentctl secret set tinyauth-google-id and '
            'agentctl secret set tinyauth-google-secret',
        )
    m = re.search(r':v?(\d+)\.(\d+)\.(\d+)$', t['image'])
    fixed = m and tuple(int(x) for x in m.groups()) >= (5, 1, 3)
    c.add(
        'tinyauth-version',
        fixed,
        f'tinyauth image {t["image"]}',
        f'use {config.TINYAUTH_IMAGE} or newer (fixes CVE-2026-77560 and GHSA-r27r-rr9v-vv37)',
        'warning',
    )
    try:
        req = urllib.request.Request(f'http://127.0.0.1:{render.INGRESS_PORT}/', headers={'Host': t['domain']})
        with urllib.request.urlopen(req, timeout=5):
            ok = True
    except Exception:  # any failure means not reachable
        ok = False
    c.add('tinyauth', ok, f'tinyauth answers on {t["domain"]}', 'agentctl apply; then agentctl status')


def coolify_check(cfg, c):
    if cfg['deploy'] != 'coolify':
        return
    if _private(cfg['coolify']['token_file']) is None:
        c.sudo('coolify', 'the Coolify API (its token is root-only)')
        return
    try:
        coolify.Api(cfg).call('GET', '/version')
        c.add('coolify', True, 'Coolify API reachable')
    except Exception as e:  # reported as a check
        c.add(
            'coolify',
            False,
            f'Coolify: {e}',
            f'create an API token in Coolify ({cfg["coolify"]["url"]} → Keys & Tokens → API tokens, permission root), '
            'then agentctl secret set coolify',
        )


def cluster(cfg, c):
    for a in cfg['agents']:
        c.add(
            f'agent-dir-{a["id"]}',
            os.path.isdir(f'{a["path"]}/home'),
            f'{a["id"]} files at {a["path"]}',
            'agentctl apply',
        )
    units = ['agentlab-disks.service', 'agentlab-throttle.service', 'agentlab-watch.service', 'agentlab-janitor.timer']
    units += ['agentlab-backup.timer'] if cfg['backups']['enabled'] else []
    units += ['agentlab-update.timer'] if cfg['updates']['agentlab'] == 'daily' else []
    for unit in [*units, 'agentlab-firewall.service']:
        c.add(f'unit-{unit}', _active(unit), f'{unit} active', 'agentctl install')
    if not cfg['backups']['enabled']:
        c.add('backups', True, 'nightly backups are off ([backups] enabled = false); `agentctl backup run` still works')
    updates(cfg, c)
    c.add('slice', os.path.isdir('/sys/fs/cgroup/agentlab.slice'), 'agentlab.slice memory cap', 'agentctl install')
    if not is_root():
        c.sudo('firewall', 'the agentlab firewall table (nft needs root)')
        rules = None
    else:
        rules = run(['nft', 'list', 'set', 'inet', 'agentlab', 'agents'], check=False)[1]
    missing = [a['id'] for a in cfg['agents'] if rules is not None and config.agent_ip(a) not in rules]
    if rules is not None:
        c.add(
            'firewall',
            not missing,
            'firewall covers every agent' if not missing else f'firewall misses {", ".join(missing)}',
            'agentctl install && agentctl apply',
        )
    for name, _, _ in deploy.networks(cfg):
        c.add(
            f'network-{name}',
            run(['docker', 'network', 'inspect', name], check=False)[0] == 0,
            f'network {name}',
            'agentctl apply',
        )
    for stack in render.stacks(cfg):
        c.add(f'stack-{stack}', bool(deploy.containers(cfg, stack)), f'{stack} running', 'agentctl apply')


def run_all(cfg):
    c = Checks()
    host(cfg, c)
    if docker(cfg, c):
        cluster(cfg, c)
    android(cfg, c)
    access(cfg, c)
    coolify_check(cfg, c)
    return c.items


def updates(cfg, c):
    """The last `agentctl update`: a failed nightly run is a warning, agents left for later are information."""
    from . import update  # noqa: PLC0415 - update imports apply, which doctor doesn't otherwise need

    if cfg['updates']['agentlab'] != 'daily':
        c.add(
            'updates', True, 'nightly self-update is off ([updates] agentlab = "off"); `agentctl update` works by hand'
        )
    last = update.last(cfg)
    if not last:
        return
    if last.get('result') == 'failed':
        c.add(
            'update-last',
            False,
            f'the last update ({last.get("at", "?")}) failed: {last.get("error", "")}',
            'fix the cause, then `agentctl update`',
            'warning' if last.get('scheduled') else 'info',
        )
    elif last.get('agents_deferred'):
        c.add(
            'update-last',
            False,
            f'the last update ({last.get("at", "?")}) left {", ".join(last["agents_deferred"])} for later: busy all window',
            'it goes on the next update, or `agentctl apply --force` now (interrupts the running turn)',
            'info',
        )
    else:
        c.add('update-last', True, f'last update {last.get("at", "?")}: {last.get("commit", "")} ok')
