"""Optional phone pushes through a Bark server (BARK_URL), driven by each agent's T3 database (read-only)."""

import os

from .bark import BARK, recent, send, server_up
from .settings import DEFAULTS, load, save, update
from .t3 import T3, newest_chat_link, thread_link
from .watcher import Watcher

watcher = None  # set by hub.py


def enabled():
    return bool(BARK) and os.environ.get('HUB_PUSHES', '1') == '1'


__all__ = [
    'BARK',
    'DEFAULTS',
    'T3',
    'Watcher',
    'enabled',
    'load',
    'newest_chat_link',
    'recent',
    'save',
    'send',
    'server_up',
    'thread_link',
    'update',
    'watcher',
]
