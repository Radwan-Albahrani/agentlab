"""The agentlab images: built locally (agentlab/<name>:latest, never pulled) or pulled from the [images] registry."""

import os

from .util import REPO, Failed, run, say

SOURCES = {'agent': 'image', 'gate': 'gate', 'hub': 'hub', 'companion': 'companion'}


def ref(cfg, name):
    images = cfg.get('images') or {}
    if images.get('registry'):
        return f'{images["registry"]}/agentlab-{name}:{images.get("tag") or "latest"}'
    return f'agentlab/{name}:latest'


def local(cfg):
    return not (cfg.get('images') or {}).get('registry')


def needed(cfg):
    """The images the cluster runs; an agent with its own `image` doesn't need ours."""
    agent = ['agent'] if any(not a.get('image') for a in cfg['agents']) else []
    return [*agent, 'gate', 'hub'] + (['companion'] if cfg['companions'] else [])


def present(image):
    return run(['docker', 'image', 'inspect', image], check=False)[0] == 0


def build(cfg, plan, names=None, force=False):
    for name in names or needed(cfg):
        image, context = ref(cfg, name), os.path.join(REPO, SOURCES[name])
        if not force and present(image):
            continue
        if not os.path.isfile(os.path.join(context, 'Dockerfile')):
            raise Failed(f'{context}/Dockerfile missing: cannot build {image}')
        plan.do(f'build {image} from {SOURCES[name]}/', ['docker', 'build', '-q', '-t', image, context])


def pull(cfg, plan, names=None):
    if local(cfg):
        raise Failed('[images] registry is empty: images are built locally (agentctl images build)')
    for name in names or needed(cfg):
        plan.do(f'pull {ref(cfg, name)}', ['docker', 'pull', '-q', ref(cfg, name)])


def ensure(cfg, plan, force=False):
    if local(cfg):
        build(cfg, plan, force=force)
    else:
        missing = [n for n in needed(cfg) if force or not present(ref(cfg, n))]
        if missing:
            pull(cfg, plan, missing)
        else:
            say('  images present')
