"""The watcher (systemd agentlab-watch): the host side of the hub. The hub and the agents run in containers and
can't touch Docker, systemd or the host's files, so this does: hub and agent requests within a second, and every 30 s
disk usage, secrets applied where they're used, the container/stack inventory and the network joins. Writes to
<data>/hub/watch.
Run: python3 -m watch (from host/), or python3 -m watch --scan for the storage breakdown."""

import sys
import threading
import time

from . import agent_requests, inventory, page_requests, secrets, storage, store
from .settings import CHECK_EVERY_S, REQUEST_POLL_S

CHECKS = (('storage', storage.check), ('secrets', secrets.check), ('containers', inventory.check))


def guarded(name, step, *args):
    """A failing step is reported on the page and the watcher keeps going."""
    try:
        step(*args)
    except Exception as e:
        store.event('watcher', f'{name} check failed', f'{type(e).__name__}: {e}', ok=False)


def checks_forever():
    while True:
        state = store.load('state.json', {})
        for name, step in CHECKS:
            guarded(name, step, state)
        store.dump('state.json', state)
        store.trim_events()
        time.sleep(CHECK_EVERY_S)


def main():
    if sys.argv[1:] == ['--scan']:
        storage.scan()
        return
    threading.Thread(target=checks_forever, daemon=True).start()  # docker ps can take seconds: requests stay snappy
    while True:
        guarded('requests', page_requests.handle_pending)
        guarded('agent requests', agent_requests.handle_all)
        time.sleep(REQUEST_POLL_S)


if __name__ == '__main__':
    main()
