"""Optional phone pushes through a Bark server (BARK_URL; off when empty), driven by each agent's T3 database
(read-only; agents don't know).
Pings when an agent asks a question / needs approval, and when a top-level chat's job finishes, stops or fails.

  settings  /data/notify.json: device key, mute, minimum minutes, encryption key
  bark      sending (optionally AES-encrypted), the recent-pushes log
  text      markdown -> notification text
  t3        reading an agent's T3 database: questions, approvals, last messages, tap-through links
  watcher   the polling thread that decides what to push"""

import os

from .bark import BARK, recent, send, server_up
from .settings import DEFAULTS, load, save, update
from .t3 import T3, newest_chat_link, thread_link
from .watcher import Watcher

watcher = None  # the running Watcher, set by hub.py


def enabled():
    return bool(BARK) and os.environ.get('HUB_PUSHES', '1') == '1'  # test instances run without the watcher


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
