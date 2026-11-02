"""Whether an agent's owner finished onboarding (signed in to Claude / Codex), asked of the agent's Accounts API.
Done never becomes undone, so `True` is cached for good; `False` only briefly, so finishing shows up within seconds.
If the agent doesn't answer, the gate lets the request through: a sick Accounts app must not lock anyone out of T3."""

import json
import logging
import threading
import time
import urllib.request

log = logging.getLogger('gate')
NOT_DONE_TTL = 10
TIMEOUT = 2


def fetch_done(upstream):
    with urllib.request.urlopen(f'{upstream.rstrip("/")}:8790/api/onboarding', timeout=TIMEOUT) as r:
        return bool(json.load(r).get('done'))


class Onboarding:
    def __init__(self, fetch=fetch_done):
        self._fetch = fetch
        self._lock = threading.Lock()
        self._done = set()
        self._not_done = {}  # agent id -> monotonic time we learned it

    def pending(self, agent_id, upstream):
        """True only when the agent said onboarding isn't done (recently). Unknown or unreachable is False."""
        with self._lock:
            if agent_id in self._done:
                return False
            seen = self._not_done.get(agent_id)
            if seen is not None and time.monotonic() - seen < NOT_DONE_TTL:
                return True
        try:
            done = self._fetch(upstream)
        except (OSError, ValueError, AttributeError) as e:
            log.warning('onboarding state of %s unknown: %s', agent_id, e)
            return False
        with self._lock:
            if done:
                self._done.add(agent_id)
                self._not_done.pop(agent_id, None)
            else:
                self._not_done[agent_id] = time.monotonic()
        return not done
