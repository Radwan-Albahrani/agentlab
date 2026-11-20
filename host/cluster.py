"""cluster.json for the host services; a missing file gives {} so they start with defaults instead of crash-looping."""

import json
import os
from typing import Literal, TypedDict

PATH = os.environ.get('AGENTLAB_CLUSTER', '/srv/agentlab/rendered/cluster.json')


# The keys the host reads; agentctl's config.public() writes them all, sections are read leniently (total=False).
class Agent(TypedDict):
    id: str
    owner: str
    path: str
    storage_unit: str  # '' = the host's filesystem


class Companion(TypedDict):
    name: str
    display_name: str
    agent: str
    kind: str


class ExtraSecrets(TypedDict, total=False):
    folder: str
    map: str
    label: str


class Hub(TypedDict, total=False):
    extra_stacks: list[str]
    extra_secrets: ExtraSecrets


class Storage(TypedDict, total=False):
    mode: Literal['shared', 'per-person']
    pool_size: str  # '' = no pool image
    pool_image: str


class Throttle(TypedDict, total=False):
    io_psi_max: float


class Limits(TypedDict, total=False):
    throttle: Throttle


class Cluster(TypedDict, total=False):
    data: str
    agents: list[Agent]
    companions: list[Companion]
    hub: Hub
    storage: Storage
    limits: Limits


def load(path: str | None = None) -> Cluster:
    try:
        with open(path or PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def data_dir(cfg: Cluster | None = None) -> str:
    return (cfg if cfg is not None else load()).get('data') or os.path.dirname(os.path.dirname(PATH))
