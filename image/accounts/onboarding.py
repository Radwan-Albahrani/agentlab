"""Onboarding state; the gate keeps T3 closed until `done` (one AI sign-in plus the owner's explicit finish)."""

import contextlib
import os
import time

import connectors
import signin
from util import HOME

MARK = os.path.join(HOME, '.config', 'agent', 'onboarded')
AI = ('claude', 'codex')


def _signed_in(flow):
    return signin.status(flow)[0]


def state():
    ai = {flow: _signed_in(flow) for flow in AI}
    ready = any(ai.values())
    steps = [
        {'id': 'claude', 'done': ai['claude'], 'optional': False},
        {'id': 'codex', 'done': ai['codex'], 'optional': False},
        {'id': 'connectors', 'done': any(connectors.signed_in(k) for k in connectors.load()), 'optional': True},
        {'id': 'github', 'done': _signed_in('github'), 'optional': True},
    ]
    return {'done': ready and os.path.exists(MARK), 'ready': ready, 'steps': steps}


def finish():
    """-> '' or why not."""
    if not any(_signed_in(flow) for flow in AI):
        return 'Sign in to Claude Code or Codex first.'
    os.makedirs(os.path.dirname(MARK), exist_ok=True)
    with open(MARK, 'w') as f:
        f.write(time.strftime('%FT%T%z') + '\n')
    return ''


def reset():
    with contextlib.suppress(FileNotFoundError):
        os.remove(MARK)
