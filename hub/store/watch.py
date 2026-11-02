"""The host watcher's output (host/watch writes <data>/hub/watch, mounted at /watch) and requests to it."""

import os
import time
from pathlib import Path

from .files import read_json, read_jsonl

WATCH = os.environ.get('WATCH_DIR', '/watch')
ALIVE_WITHIN = 120  # s: older numbers mean the watcher has stopped


def usage():
    return read_json(os.path.join(WATCH, 'usage.json'), {})


def containers():
    return read_json(os.path.join(WATCH, 'containers.json'), {})


def container_names():
    """Containers the page may restart or read logs of: agentlab's and the extra stacks' (domains.known)."""
    import domains  # noqa: PLC0415 - domains reads this module

    return {r['name'] for r in containers().get('items') or [] if domains.known(r.get('stack') or 'other')}


def events(kinds=None, limit=200):
    ev = read_jsonl(os.path.join(WATCH, 'events.jsonl'), 1000)
    return [e for e in ev if not kinds or e.get('kind') in kinds][:limit]


def alive():
    return time.time() - usage().get('at', 0) < ALIVE_WITHIN


def logs(container):
    """The tail the watcher last wrote for a container (after a logs~<name> request): (text, written at)."""
    p = Path(WATCH, 'logs', os.path.basename(container) + '.txt')
    try:
        return p.read_text(encoding='utf-8', errors='replace'), p.stat().st_mtime
    except OSError:
        return '', 0


def people():
    """Per-person storage: {owner email: {size, used, avail}} of each person's own disk (None while not mounted)."""
    return {k.lower(): v for k, v in (usage().get('people') or {}).items()}


def companion_container(name):
    """The container of a companion (stack agentlab-companion-<name>), or None."""
    for r in containers().get('items') or []:
        if r.get('stack') == f'agentlab-companion-{name}' or r['name'] == f'companion-{name}':
            return r['name']
    return None


def request(name):
    """Ask the watcher to do something on the host; it picks requests up within about a second."""
    folder = os.path.join(WATCH, 'requests')
    os.makedirs(folder, exist_ok=True)
    Path(folder, name).touch()
