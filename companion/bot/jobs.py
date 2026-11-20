"""Background threads, so Slack event handlers return at once."""

import threading
from collections.abc import Callable


def run_later[*Ts](fn: Callable[[*Ts], object], *args: *Ts) -> None:
    threading.Thread(target=fn, args=args, daemon=True).start()
