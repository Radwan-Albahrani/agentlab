"""Onboarding: a new agent's owner signs in to Claude Code and/or Codex (their own accounts), adds connectors and
optionally GitHub, then finishes. The gate keeps T3 closed until `done`, so it needs at least one AI sign-in AND the
owner's explicit finish (~/.config/agent/onboarded); the hub draws the steps from GET /api/onboarding."""

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
    # claude and codex aren't optional, but one of the two is enough: `ready` says whether finishing is allowed.
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
