"""cluster.json (written by `agentctl apply`) for the host services. Its path comes from AGENTLAB_CLUSTER, which
the systemd units set; a missing file gives {} so the services start with defaults instead of crash-looping."""

import json
import os

PATH = os.environ.get('AGENTLAB_CLUSTER', '/srv/agentlab/rendered/cluster.json')


def load(path=None):
    try:
        with open(path or PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def data_dir(cfg=None):
    return (cfg if cfg is not None else load()).get('data') or os.path.dirname(os.path.dirname(PATH))
