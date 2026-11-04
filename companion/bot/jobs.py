"""Background threads, so Slack event handlers return at once."""

import threading


def run_later(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()
