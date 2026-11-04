"""The hub's host side: does the Docker, systemd and file work the containerized hub and agents can't."""

import sys
import threading
import time

from . import agent_requests, inventory, page_requests, secrets, storage, store
from .settings import CHECK_EVERY_S, REQUEST_POLL_S

CHECKS = (('storage', storage.check), ('secrets', secrets.check), ('containers', inventory.check))


def guarded(name, step, *args):
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
    threading.Thread(target=checks_forever, daemon=True).start()  # docker ps is slow; keeps requests snappy
    while True:
        guarded('requests', page_requests.handle_pending)
        guarded('agent requests', agent_requests.handle_all)
        time.sleep(REQUEST_POLL_S)


if __name__ == '__main__':
    main()
