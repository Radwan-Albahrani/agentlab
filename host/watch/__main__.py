"""The hub's host side: does the Docker, systemd and file work the containerized hub and agents can't."""

import sys
import threading
import time
from collections.abc import Callable

from . import agent_requests, inventory, jobs, page_requests, secrets, storage, store
from .settings import CHECK_EVERY_S, REQUEST_POLL_S

CHECKS: tuple[tuple[str, Callable[[store.State], None]], ...] = (
    ('storage', storage.check),
    ('secrets', secrets.check),
    ('containers', inventory.check),
)


def guarded(name: str, step: Callable[..., object], *args: object) -> None:
    try:
        step(*args)
    except Exception as e:
        store.event('watcher', f'{name} check failed', f'{type(e).__name__}: {e}', ok=False)


def checks_forever() -> None:
    while True:
        state: store.State = store.load('state.json', {})
        for name, step in CHECKS:
            guarded(name, step, state)
        store.dump('state.json', state)
        store.trim_events()
        time.sleep(CHECK_EVERY_S)


def main() -> None:
    if sys.argv[1:] == ['--scan']:
        storage.scan()
        return
    threading.Thread(target=checks_forever, daemon=True).start()  # docker ps is slow; keeps requests snappy
    while True:
        guarded('requests', page_requests.handle_pending)
        guarded('agent requests', agent_requests.handle_all)
        guarded('agent management', jobs.tick)
        time.sleep(REQUEST_POLL_S)


if __name__ == '__main__':
    main()
