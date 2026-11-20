"""The compose files agentctl rendered from cluster.toml (read-only; edits belong in cluster.toml)."""

import os
from pathlib import Path
from typing import Any

RENDERED = os.environ.get('RENDERED_DIR', '/rendered')


def _compose(sid: str) -> str:
    return os.path.join(RENDERED, 'compose', sid, 'docker-compose.yml')


def stacks() -> list[dict[str, Any]]:
    root = os.path.join(RENDERED, 'compose')
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return []
    return [{'id': n, 'modified': os.path.getmtime(_compose(n))} for n in names if os.path.isfile(_compose(n))]


def read(sid: str) -> str:
    if sid not in {s['id'] for s in stacks()}:
        raise ValueError('Unknown stack.')
    return Path(_compose(sid)).read_text(encoding='utf-8')
