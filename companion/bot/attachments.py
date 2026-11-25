"""The files on an outgoing ledger message, each in its own explicit state (fsm.ATTACHMENT).

check() runs them through the gate once: ready or held. Whoever sends the message marks its ready files sent or
failed (sent / failed below) before moving it to sent, and ledger.move withholds them when the message never goes,
so no message is ever recorded as sent while its files stayed behind."""

import os
from typing import Literal

from . import gate, slack
from .config import log
from .fsm import ATTACHMENT
from .shapes import Attachment, Item


def check(it: Item, box: str) -> list[str]:
    """Gate the item's files into it['attachments']; returns the paths of the ready ones."""
    out: list[Attachment] = []
    for name in it.get('files') or []:
        path, why = gate.one(box, name)
        out.append(
            {
                'name': os.path.basename(str(name)),
                'path': path,
                'state': ATTACHMENT.first('ready' if path else 'held'),
                'note': why,
            }
        )
    it['attachments'] = out
    return ready(it)


def _all(it: Item) -> list[Attachment]:
    return it.get('attachments') or []


def ready(it: Item) -> list[str]:
    """Paths of the files still waiting to go with the message."""
    return [a['path'] for a in _all(it) if ATTACHMENT.is_(a['state'], 'ready')]


def settle(it: Item, state: Literal['sent', 'failed', 'withheld'], note: str = '') -> None:
    """Every ready file of the message to `state`."""
    for a in _all(it):
        if ATTACHMENT.is_(a['state'], 'ready'):
            a['state'] = ATTACHMENT.to(a['state'], state)
            a['note'] = note


def upload(it: Item, places: list[tuple[str, str | None]], comment: str | None = None) -> None:
    """Upload the message's ready files to each (channel, thread) its message went to: sent, or failed with Slack's
    reason."""
    try:
        for channel, thread_ts in places:
            slack.upload(channel, thread_ts, ready(it), comment)
    except Exception as e:
        log('upload failed:', e)
        settle(it, 'failed', f"Slack didn't take it: {str(e)[:150]}")
        return
    settle(it, 'sent')


def held(it: Item) -> str:
    """'run.sh (file type not allowed), x.pdf (missing)': the files the gate kept back, for people."""
    return ', '.join(f'{a["name"]} ({a["note"]})' for a in _all(it) if ATTACHMENT.is_(a['state'], 'held'))


def summary(it: Item) -> str:
    """'a.xlsx sent · run.sh held (file type not allowed)': every file of the message and its state, for people."""
    return ' · '.join(f'{a["name"]} {a["state"]}' + (f' ({a["note"]})' if a['note'] else '') for a in _all(it))


def described(paths: list[str]) -> str:
    """'2 files: a.xlsx, b.zip'."""
    names = [os.path.basename(p) for p in paths]
    return f'{len(names)} file{"s" if len(names) != 1 else ""}: {", ".join(names)}'
