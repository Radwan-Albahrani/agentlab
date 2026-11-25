"""Start-up: Slack Socket Mode, the main poller and the faster asks poller."""

import os
import threading
import time
from collections.abc import Callable

from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.web import SlackResponse

from . import (  # noqa: F401  (routing registers the handlers)
    asks,
    drafts,
    machine,
    mirror,
    outbox,
    polls,
    publish,
    requests,
    reviews,
    routing,
    slack,
    tasks,
)
from .config import AGENT, ASKS_POLL, BRIDGE, COMP, DATA, FILES, NAME, OWNER, POLL, log, mode, secret
from .state import lock, save, state


def _guarded[*Ts](label: str, fn: Callable[[*Ts], object], *args: *Ts) -> bool:
    try:
        fn(*args)
    except Exception as e:
        log(f'{label} failed:', type(e).__name__, str(e)[:300])
        return False
    return True


def poll() -> None:
    while True:
        time.sleep(POLL)
        for task in list(state['tasks'].values()):
            with lock:
                _guarded(f'tick {task.get("thread")}', outbox.tick, task)  # must run before tasks.tick
                _guarded(f'tick {task.get("thread")}', tasks.tick, task)
        with lock:
            _guarded('reviews', reviews.tick)
        _guarded('evidence', reviews.prune_tick)
        with lock:
            _guarded('polls', polls.tick)
        _guarded('requests', requests.pending_tick)
        _guarded('invites', requests.invite_tick)
        if time.time() >= state.get('_drafts_retry', 0):
            with lock:
                if not _guarded('drafts', drafts.tick):
                    state['_drafts_retry'] = time.time() + 300
        save()
        _guarded('publish', publish.tick)


def watch_asks() -> None:
    while True:
        time.sleep(ASKS_POLL)
        _guarded('asks', asks.tick)


def watch_pulls() -> None:
    """Keep the open PRs fresh on their own, so the hub's list never waits on GitHub (the hub's Refresh still asks)."""
    while True:
        _guarded('pull requests', asks.refresh_pulls)
        time.sleep(reviews.PULLS_EVERY)


def watch_mirrors() -> None:
    """Re-sync live case threads, for any change Slack's events missed (mirror.py)."""
    while True:
        time.sleep(mirror.SWEEP_EVERY)
        _guarded('mirrors', mirror.sweep)


def _check_scopes(me: SlackResponse) -> None:
    """Say on the hub when the Slack app lacks scopes its manifest asks for: without them messages go unseen."""
    tokens = [('bot', me)]
    if slack.USER:
        try:
            tokens.append(('user', slack.USER.auth_test()))
        except Exception as e:
            log('user token check failed:', e)
    for kind, r in tokens:
        missing = slack.missing_scopes(r, kind)
        if missing:
            log(f'Slack {kind} token is missing scopes:', ', '.join(missing))
            COMP.event(
                'failed',
                f'The Slack app is missing {kind} scopes: {", ".join(missing)}',
                detail=f'Add them under OAuth & Permissions ({kind} token scopes), then reinstall the app. Until then '
                'some messages are never seen.',
                ok=False,
            )


def run() -> None:
    for d in (DATA, FILES, drafts.DRAFTS, outbox.OUTBOX):
        os.makedirs(d, exist_ok=True)
    machine.prepare_all(list(state['tasks'].values()))
    log(f'{NAME} for {AGENT}: owner {OWNER}, bridge {BRIDGE}, {len(state["tasks"])} known threads, mode {mode()}')
    me = slack.app.client.auth_test()  # also verifies the bot token
    slack.WORKSPACE = me['url']
    COMP.event('live', f'{NAME} started', detail=f'mode: {mode()}')
    _check_scopes(me)
    threading.Thread(target=poll, daemon=True).start()
    threading.Thread(target=watch_asks, daemon=True).start()
    threading.Thread(target=watch_pulls, daemon=True).start()
    threading.Thread(target=watch_mirrors, daemon=True).start()
    handler = publish.handler = SocketModeHandler(slack.app, secret('app-token.txt'))
    handler.start()
