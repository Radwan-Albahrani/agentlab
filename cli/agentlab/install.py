"""`agentctl install`: one-time host setup, by the numbered steps in host/install/. Each step checks before it
changes anything and prints what it changed, so re-running is safe; then the images are built (or pulled)."""

import glob
import os
import subprocess

from . import config, images
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
        'AGENTLAB_HUB_PORT': str(cfg['auth']['hub_port']),
        'AGENTLAB_ANDROID': '1' if cfg['android']['enabled'] else '',
        'AGENTLAB_SYSTEM_IMAGE': cfg['android']['system_image'],
        'AGENTLAB_MEMORY_MAX': str(total),
        'AGENTLAB_MEMORY_HIGH': str(max(total - 2 * 2**30, int(total * 0.9))),  # where the kernel starts reclaiming
        'AGENTLAB_BACKUP_TIME': cfg['backups']['time'],
        'AGENTLAB_BACKUPS': '1' if cfg['backups']['enabled'] else '',
        'AGENTLAB_SERVE': '' if config.ports_only(cfg) else '1',  # published-ports setups never touch tailscale serve
        'AGENTLAB_COOLIFY_TOKEN': cfg['coolify']['token_file'],
        'AGENTLAB_COOLIFY_URL': cfg['coolify']['url'],
        'AGENTLAB_TUNNEL_TOKEN': f'{cfg["data"]}/secrets/cloudflare-tunnel.token',
    }


def steps():
    return sorted(glob.glob(os.path.join(REPO, 'host', 'install', '[0-9][0-9]-*.sh')))


def install(cfg, config_path, only=None, skip_images=False):
    need_root('agentctl install')
    env = step_env(cfg, config_path)
    manual = []
    for path in steps():
        name = os.path.basename(path)[3:-3]
        if only and name not in only:
            continue
        say(f'== {name}')
        # People watch long steps (Docker, the Android SDK) live; agents get the output in the JSON at the end.
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
        raise Needs(f'manual steps needed ({", ".join(manual)}): see above, then re-run agentctl install')
    return {'steps': [os.path.basename(p)[3:-3] for p in steps()]}
