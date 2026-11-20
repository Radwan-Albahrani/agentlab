"""The agentlab images: built locally (agentlab/<name>:latest, never pulled) or pulled from the [images] registry."""

import os
from typing import Literal

from .config import Cluster
from .util import REPO, Failed, Plan, run, say

ImageName = Literal['agent', 'gate', 'hub', 'companion']
SOURCES: dict[ImageName, str] = {'agent': 'image', 'gate': 'gate', 'hub': 'hub', 'companion': 'companion'}


def ref(cfg: Cluster, name: ImageName) -> str:
    images = cfg.get('images') or {}
    if images.get('registry'):
        return f'{images["registry"]}/agentlab-{name}:{images.get("tag") or "latest"}'
    return f'agentlab/{name}:latest'


def local(cfg: Cluster) -> bool:
    return not (cfg.get('images') or {}).get('registry')


def needed(cfg: Cluster) -> list[ImageName]:
    """The images the cluster runs; an agent with its own `image` doesn't need ours."""
    agent: list[ImageName] = ['agent'] if any(not a.get('image') for a in cfg['agents']) else []
    return [*agent, 'gate', 'hub'] + (['companion'] if cfg['companions'] else [])


def present(image: str) -> bool:
    return run(['docker', 'image', 'inspect', image], check=False)[0] == 0


def build(cfg: Cluster, plan: Plan, names: list[ImageName] | None = None, force: bool = False) -> None:
    for name in names or needed(cfg):
        image, context = ref(cfg, name), os.path.join(REPO, SOURCES[name])
        if not force and present(image):
            continue
        if not os.path.isfile(os.path.join(context, 'Dockerfile')):
            raise Failed(f'{context}/Dockerfile missing: cannot build {image}')
        plan.do(f'build {image} from {SOURCES[name]}/', ['docker', 'build', '-q', '-t', image, context])


def pull(cfg: Cluster, plan: Plan, names: list[ImageName] | None = None) -> None:
    if local(cfg):
        raise Failed('[images] registry is empty: images are built locally (agentctl images build)')
    for name in names or needed(cfg):
        plan.do(f'pull {ref(cfg, name)}', ['docker', 'pull', '-q', ref(cfg, name)])


def ensure(cfg: Cluster, plan: Plan, force: bool = False) -> None:
    if local(cfg):
        build(cfg, plan, force=force)
    else:
        missing = [n for n in needed(cfg) if force or not present(ref(cfg, n))]
        if missing:
            pull(cfg, plan, missing)
        else:
            say('  images present')
