"""Work that may wait on Slack or T3 runs in the background, so Slack's event handlers return at once."""

import threading


def run_later(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()
