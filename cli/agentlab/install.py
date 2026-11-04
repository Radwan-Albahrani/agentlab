"""`agentctl install`: one-time host setup via the host/install/ steps, then the images."""

import glob
import os
import subprocess

from . import cloudflare, config, images, preflight
from .util import OUT, REPO, Failed, Needs, Plan, need_root, say, size_bytes


def step_env(cfg, config_path):
    total = size_bytes(cfg['limits']['total_memory'])
    return {
        **os.environ,
        'AGENTLAB_REPO': REPO,
        'AGENTLAB_CONFIG': os.path.abspath(config_path),
        'AGENTLAB_DATA': cfg['data'],
        'AGENTLAB_DEPLOY': cfg['deploy'],
        'AGENTLAB_ISOLATION': cfg['isolation'],
        'AGENTLAB_MODE': cfg['auth']['mode'],
        'AGENTLAB_INGRESS': cfg['auth']['ingress'],
        'AGENTLAB_CF_NETWORK': 'private' if config.private_network(cfg) else '',
        'AGENTLAB_HUB_PORT': str(cfg['auth']['hub_port']),
        'AGENTLAB_ANDROID': '1' if cfg['android']['enabled'] else '',
        'AGENTLAB_SYSTEM_IMAGE': cfg['android']['system_image'],
        'AGENTLAB_MEMORY_MAX': str(total),
        'AGENTLAB_MEMORY_HIGH': str(max(total - 2 * 2**30, int(total * 0.9))),
        'AGENTLAB_BACKUP_TIME': cfg['backups']['time'],
        'AGENTLAB_BACKUPS': '1' if cfg['backups']['enabled'] else '',
        'AGENTLAB_UPDATE_TIME': cfg['updates']['time'],
        'AGENTLAB_UPDATES': '1' if cfg['updates']['agentlab'] == 'daily' else '',
        'AGENTLAB_SERVE': '' if config.ports_only(cfg) else '1',
        'AGENTLAB_COOLIFY_TOKEN': cfg['coolify']['token_file'],
        'AGENTLAB_COOLIFY_URL': cfg['coolify']['url'],
        'AGENTLAB_COOLIFY_DOMAIN': cfg['coolify_domain'],
        'AGENTLAB_ADMIN_EMAIL': cfg['auth']['admins'][0],
        'AGENTLAB_TUNNEL_TOKEN': f'{cfg["data"]}/secrets/cloudflare-tunnel.token',
    }


def tunnel_first(cfg, env, config_path):
    """Create the tunnel token before the cloudflared step when the API token is saved."""
    if cfg['auth']['ingress'] != 'cloudflared' or os.path.exists(env['AGENTLAB_TUNNEL_TOKEN']):
        return
    if not os.path.exists(cfg['cloudflare']['api_token_file']):
        return
    say('  creating the Cloudflare tunnel first (agentctl cloudflare setup)')
    cloudflare.setup(cfg, Plan(False), config_path)


def steps():
    return sorted(glob.glob(os.path.join(REPO, 'host', 'install', '[0-9][0-9]-*.sh')))


def install(cfg, config_path, only=None, skip_images=False):
    need_root('agentctl install')
    blocked = preflight.problems(cfg, refresh=True)
    if blocked:
        raise Needs('; '.join(f'{message} (fix: {fix})' for _, message, fix in blocked))
    env = step_env(cfg, config_path)
    manual = []
    for path in steps():
        name = os.path.basename(path)[3:-3]
        if only and name not in only:
            continue
        say(f'== {name}')
        if name == 'cloudflared':
            tunnel_first(cfg, env, config_path)
        p = subprocess.run(['bash', path], env=env, check=False, capture_output=OUT.json, text=True)
        for line in ((p.stdout or '') + (p.stderr or '')).splitlines():
            say(f'  {line}')
        if p.returncode == 2:
            manual.append(name)
        elif p.returncode:
            raise Failed(f'install step {name} failed (exit {p.returncode})')
    if not skip_images and not only:
        say('== images')
        images.ensure(cfg, Plan(False))
    if manual:
        raise Needs(f'steps that need you ({", ".join(manual)}): see above, then run agentctl setup again')
    return {'steps': [os.path.basename(p)[3:-3] for p in steps()]}
