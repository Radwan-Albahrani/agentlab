"""The compose files agentctl rendered from cluster.toml (<data>/rendered/compose/<stack>/docker-compose.yml, mounted
read-only at /rendered). They are shown as they are: a change goes into cluster.toml and `agentctl apply`, which
re-renders them, so editing them here would be lost."""

import os
from pathlib import Path

RENDERED = os.environ.get('RENDERED_DIR', '/rendered')


def _compose(sid):
    return os.path.join(RENDERED, 'compose', sid, 'docker-compose.yml')


def stacks():
    """[{id, modified}] of every rendered stack, sorted by id."""
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
