"""The compose files agentctl rendered from cluster.toml (read-only; edits belong in cluster.toml)."""

import os
from pathlib import Path

RENDERED = os.environ.get('RENDERED_DIR', '/rendered')


def _compose(sid):
    return os.path.join(RENDERED, 'compose', sid, 'docker-compose.yml')


def stacks():
    root = os.path.join(RENDERED, 'compose')
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return []
    return [{'id': n, 'modified': os.path.getmtime(_compose(n))} for n in names if os.path.isfile(_compose(n))]


def read(sid):
    if sid not in {s['id'] for s in stacks()}:
        raise ValueError('Unknown stack.')
    return Path(_compose(sid)).read_text(encoding='utf-8')
