"""`agentctl apply`: idempotent; every step reads current state and changes only what differs."""

import datetime
import json
import os
import secrets
import shutil
import subprocess

from . import cloudflare, config, deploy, disks, health, hostsfile, images, render, template, wslhost
from .util import AGENT_UID, REPO, Plan, agent_folder, differs, need_root, run, say, warn, write_if_changed

FIREWALL_UNIT = 'agentlab-firewall.service'


def folders(cfg, plan):
    data = cfg['data']
    # hub/data holds phone-push keys: root only.
    private = [f'{data}/secrets', f'{data}/secrets/agents', f'{data}/secrets/companions', f'{data}/backups']
    private.append(f'{data}/hub/data')
    shared = [
        f'{data}/disks',
        f'{data}/shared',
        f'{data}/rendered',
        f'{data}/hub',
        f'{data}/hub/watch',
        f'{data}/hub/watch/requests',
        f'{data}/companions',
    ]
    if cfg['storage']['mode'] == 'per-person':
        shared.append(f'{data}/people')
    elif not cfg['storage']['pool_size']:
        shared.append(f'{data}/agents')
    if cfg['auth']['ingress'] == 'public' or config.private_https(cfg):
        private.append(f'{data}/edge-acme')
    for path in private + shared:
        if not os.path.isdir(path):
            mode = 0o700 if path in private else 0o755
            plan.do(f'create {path}', fn=lambda p=path, m=mode: os.makedirs(p, mode=m, exist_ok=True))


def _owned(path, mode=0o755):
    """Create path and missing parents owned by the agent user (else Docker creates them as root)."""
    missing = []
    while not os.path.exists(path):
        missing.append(path)
        path = os.path.dirname(path)
    for p in reversed(missing):
        os.mkdir(p, mode)
        os.chown(p, AGENT_UID, AGENT_UID)


def _secret_file(path, text, owner=None):
    with open(path + '.tmp', 'w') as f:
        f.write(text)
    os.chmod(path + '.tmp', 0o600)
    if owner is not None:
        os.chown(path + '.tmp', owner, owner)
    os.replace(path + '.tmp', path)


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ''


def agent_files(cfg, a, plan):
    env = f'{cfg["data"]}/secrets/agents/{a["id"]}.env'
    if not os.path.exists(env):
        plan.do(f"create {env} (the agent's extra environment, empty)", fn=lambda: _secret_file(env, ''))
    userdata = f'{a["path"]}/home/.t3/userdata'  # must exist before deploy, or Docker creates it as root
    if not os.path.isdir(userdata):
        plan.do(f'create {userdata}', fn=lambda: _owned(userdata))
    folder, text = render.files_data(cfg, a), render.files_config(cfg)
    if differs(f'{folder}/config.yaml', text):
        plan.do(f'write the file manager config for {a["id"]}', fn=lambda: _files_config(folder, text))


def _files_config(folder, text):
    _owned(folder)
    _secret_file(f'{folder}/config.yaml', text, AGENT_UID)


def core_files(cfg, plan):
    if cfg['auth']['mode'] == 'tinyauth':
        path = f'{cfg["data"]}/secrets/tinyauth-secret.txt'
        if not os.path.exists(path):
            plan.do('create the tinyauth session secret', fn=lambda: _secret_file(path, secrets.token_hex(16)))
    if config.private_network(cfg):
        tunnel_token_copy(cfg, plan)
    if config.private_https(cfg) and not cloudflare.gate_secret(cfg, 'key'):
        # rotating it signs everyone out
        plan.do(
            "create the gate's session key",
            fn=lambda: cloudflare.save_gate_secret(cfg, 'key', secrets.token_hex(32)),
        )


def tunnel_token_copy(cfg, plan):
    """Copy of the root-only tunnel token readable by cloudflared's uid."""
    src = f'{cfg["data"]}/secrets/cloudflare-tunnel.token'
    folder = f'{cfg["data"]}/{render.TUNNEL_TOKEN_DIR}'
    dst = f'{folder}/token'
    try:
        with open(src) as f:
            token = f.read().strip()
    except FileNotFoundError:
        return
    try:
        with open(dst) as f:
            if f.read() == token and os.stat(dst).st_uid == render.CLOUDFLARED_UID:
                return
    except OSError:
        pass

    def write():
        os.makedirs(folder, mode=0o700, exist_ok=True)
        write_if_changed(dst, token, mode=0o400)
        for path, mode in ((dst, 0o400), (folder, 0o500)):
            os.chown(path, render.CLOUDFLARED_UID, render.CLOUDFLARED_UID)
            os.chmod(path, mode)

    plan.do('give the tunnel container its copy of the tunnel token', fn=write)


def upstream_ref():
    rc, out = run(['git', '-C', REPO, 'remote', 'get-url', 'origin'], check=False)
    return out.strip() if rc == 0 and out.strip() else REPO


def version():
    rc, out = run(['git', '-C', REPO, 'describe', '--tags', '--always', '--dirty'], check=False)
    return out.strip() if rc == 0 and out.strip() else 'dev'


def seed_companion(cfg, comp):
    """Seed the agent's companion checkout from companion/ once; later template changes arrive via template.py."""
    dst = render.companion_checkout(cfg, comp)
    shutil.copytree(
        os.path.join(REPO, 'companion'),
        dst,
        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.pytest_cache', 'node_modules'),
    )
    git = ['git', '-C', dst, '-c', 'user.name=agentlab', '-c', 'user.email=agentlab@localhost']
    for cmd in (
        ['init', '-q', '-b', 'main'],
        ['add', '-A'],
        ['commit', '-q', '-m', f'from agentlab {version()}'],
        ['branch', 'template'],
        ['remote', 'add', 'upstream', upstream_ref()],
    ):
        run([*git, *cmd])
    subprocess.run(['chown', '-R', f'{AGENT_UID}:{AGENT_UID}', dst], check=True)


def companion_files(cfg, comp, plan):
    data, name = cfg['data'], comp['name']
    a = next(x for x in cfg['agents'] if x['id'] == comp['agent'])
    home = a['path']
    for path in (
        f'{data}/companions/{name}',
        f'{home}/home/.t3/userdata',
        f'{home}/workspace/.companion',
        f'{home}/home/.config/agent',
        f'{home}/workspace/companions',
        f'{data}/secrets/companions/{name}',
    ):
        if not os.path.isdir(path):
            mode = 0o700 if '/secrets/' in path else 0o755
            plan.do(f'create {path}', fn=lambda p=path, m=mode: _owned(p, m))
    checkout = render.companion_checkout(cfg, comp)
    if not os.path.exists(checkout):
        plan.do(
            f'seed {checkout} from companion/ (once; the agent owns it after)', fn=lambda: seed_companion(cfg, comp)
        )
    mine = f'{data}/secrets/companions/{name}/agent-key.txt'
    theirs = f'{home}/home/.config/agent/bridge-key'
    if not os.path.exists(mine) or not os.path.exists(theirs):

        def make():
            key = _read(mine) or _read(theirs) or secrets.token_hex(32)
            _secret_file(mine, key, AGENT_UID)
            _secret_file(theirs, key, AGENT_UID)

        plan.do(f'create the bridge key shared by {name} and agent {a["id"]}', fn=make)


def companion_list(cfg, a):
    return [{k: c[k] for k in ('name', 'display_name', 'kind')} for c in cfg['companions'] if c['agent'] == a['id']]


def companion_lists(cfg, plan):
    """~/.agentlab/companions.json in each agent, read by the in-container `companion` command."""
    for a in cfg['agents']:
        home = f'{a["path"]}/home'
        text = json.dumps(companion_list(cfg, a), indent=1) + '\n'
        if not os.path.isdir(home):
            continue
        try:
            with agent_folder(home, '.agentlab', create=False) as f:
                if f.read('companions.json') == text:
                    continue
        except FileNotFoundError:
            pass
        plan.do(f'update the companion list of {a["id"]}', fn=lambda h=home, t=text: _write_list(h, t))


def _write_list(home, text):
    with agent_folder(home, '.agentlab') as f:
        f.write('companions.json', text)


SIGN_INS = (('.claude', '.credentials.json'), ('.codex', 'auth.json'))


def signed_in(home):
    """Whether this home has a Claude Code or Codex login (~/.claude.json counts only with oauthAccount)."""
    for folder, name in SIGN_INS:
        try:
            with agent_folder(home, folder, create=False) as f:
                if f.read(name) is not None:
                    return True
        except FileNotFoundError:
            pass
    with agent_folder(home, '', create=False) as f:
        text = f.read('.claude.json', limit=16 * 2**20)
    try:
        return bool(text and json.loads(text).get('oauthAccount'))
    except (ValueError, AttributeError):
        return False


def adopt(a, plan):
    """Mark an agent with existing AI sign-ins as onboarded; False when there is nothing to adopt."""
    home = f'{a["path"]}/home'
    if not os.path.isdir(home) or not signed_in(home):
        return False
    try:
        with agent_folder(home, '.config/agent', create=False) as f:
            if f.exists('onboarded'):
                return False
    except FileNotFoundError:
        pass

    def write():
        with agent_folder(home, '.config/agent') as f:
            f.write(
                'onboarded',
                json.dumps(
                    {'at': datetime.datetime.now(datetime.UTC).isoformat(timespec='seconds'), 'by': 'agentctl adopt'}
                )
                + '\n',
            )

    plan.do(f'mark {a["id"]} onboarded (it already has AI sign-ins)', fn=write)
    return True


def write_rendered(cfg, plan):
    changed = []
    for rel, text in render.all_files(cfg).items():
        path = os.path.join(cfg['data'], 'rendered', rel)
        if differs(path, text):
            changed.append(rel)
            plan.do(f'write rendered/{rel}', fn=lambda p=path, t=text: write_if_changed(p, t))
    return changed


def firewall(cfg, changed, plan):
    if 'firewall/agentlab.nft' not in changed:
        return
    if run(['systemctl', 'is-enabled', FIREWALL_UNIT], check=False)[0] == 0:
        plan.do('load the firewall rules', ['systemctl', 'restart', FIREWALL_UNIT])
    else:
        warn(f'{FIREWALL_UNIT} is not installed: agents are not firewalled until `agentctl install` runs')


HOST_SERVICES = ('agentlab-watch.service', 'agentlab-throttle.service')


def code_changed_at(folder=None):
    folder = folder or os.path.join(REPO, 'host')
    newest = 0.0
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', 'tests')]
        newest = max([newest, *(os.path.getmtime(os.path.join(root, f)) for f in files if f.endswith('.py'))])
    return newest


def started_at(unit):
    """When the unit last started (epoch), or None when it isn't running."""
    if run(['systemctl', 'is-active', '-q', unit], check=False)[0] != 0:
        return None
    rc, out = run(['systemctl', 'show', '--timestamp=unix', '-p', 'ActiveEnterTimestamp', '--value', unit], check=False)
    return float(out.strip()[1:]) if rc == 0 and out.strip().startswith('@') else None


def host_services(plan, changed=None):
    """Restart the watcher/throttle if they started before their code last changed."""
    changed = code_changed_at() if changed is None else changed
    for unit in HOST_SERVICES:
        since = started_at(unit)
        if since is not None and since < changed:
            plan.do(f'restart {unit} onto its new code', ['systemctl', 'restart', unit])


def apply(cfg, config_path, dry=False, stack=None, build=False, only=None, force=False):
    """`only`: deploy just these stacks; `force`: redeploy all, even agents mid-turn."""
    plan = Plan(dry)
    if not dry:
        need_root('agentctl apply')
    say(f'{"Dry run: " if dry else ""}{cfg["name"]}: {len(cfg["agents"])} agents, deploy via {cfg["deploy"]}')
    access = cfg['auth']['cloudflare']
    if cfg['auth']['mode'] == 'cloudflare-access' and not (access['team'] and access['audience']):
        warn('Cloudflare Access is not set up yet, so the gate lets nobody in: run agentctl cloudflare setup')
    first = not os.path.exists(os.path.join(cfg['data'], 'rendered', 'cluster.json'))
    existing = [a for a in cfg['agents'] if os.path.isdir(f'{a["path"]}/home')] if first else []
    folders(cfg, plan)
    if not dry and cfg.get('seed'):
        from .companions import persist_seeds  # noqa: PLC0415 - companions imports this module

        persist_seeds(cfg)
    disks.ensure(cfg, plan)
    for a in cfg['agents']:
        agent_files(cfg, a, plan)
    core_files(cfg, plan)
    for comp in cfg['companions']:
        companion_files(cfg, comp, plan)
    deploy.ensure_networks(cfg, plan)
    files = render.all_files(cfg)
    changed = write_rendered(cfg, plan)
    firewall(cfg, changed, plan)
    host_services(plan)
    hostsfile.ensure([], plan)
    wslhost.ensure(cfg, plan)
    images.ensure(cfg, plan, force=build)
    for name, (kind, key) in render.stacks(cfg).items():
        if only is not None and name not in only:
            continue
        if dry:
            reason, skip = deploy.why_deploy(
                cfg, name, files[f'compose/{name}/docker-compose.yml'], force or name == stack
            )
            if skip:
                say(f'  {skip}')
            if reason:
                plan.do(f'deploy {name}' + (f' ({reason})' if reason.startswith('newer image') else ''))
            continue
        deploy.deploy(cfg, name, kind, key, plan, force=force or name == stack)
    companion_lists(cfg, plan)
    for a in existing:
        adopt(a, plan)
    deploy.connect(cfg, plan)
    deploy.isolate(cfg, plan)
    templates = {}
    if only is None:
        cloudflare.sync_people(cfg, plan)
        cloudflare.finish_https(cfg, plan)
        deploy.orphans(cfg)
        templates = template.update_all(cfg, plan)
    if not dry and not changed:
        say('  rendered files unchanged')
    if not dry and only is None:
        health.wait_ready(cfg)
    return {'changed_files': changed, 'companion_templates': templates}
