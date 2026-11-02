"""Start the companion: Slack Socket Mode (connects out, nothing is exposed) plus one poller that, every few seconds,
moves every task forward, picks up the agents' outbox files and drafts, takes asks from the hub, starts
queued pull request reviews, closes polls that are due, and refreshes what the hub shows."""

import os
import threading
import time

from slack_bolt.adapter.socket_mode import SocketModeHandler

from . import (  # noqa: F401  (routing registers the handlers)
    asks,
    drafts,
    outbox,
    polls,
    publish,
    requests,
    reviews,
    routing,
    slack,
    tasks,
)
from .config import AGENT, BRIDGE, COMP, DATA, FILES, NAME, OWNER, POLL, log, mode, secret
from .state import lock, prepare_for_start, save, state


def _guarded(label, fn, *args):
    try:
        fn(*args)
    except Exception as e:
        log(f'{label} failed:', type(e).__name__, str(e)[:300])
        return False
    return True


def poll():
    while True:
        time.sleep(POLL)
        for task in list(state['tasks'].values()):
            with lock:
                _guarded(f'tick {task.get("thread")}', outbox.tick, task)  # files first, then the answer
                _guarded(f'tick {task.get("thread")}', tasks.tick, task)
        _guarded('asks', asks.tick)
        with lock:
            _guarded('reviews', reviews.tick)
        _guarded('evidence', reviews.prune_tick)
        with lock:
            _guarded('polls', polls.tick)
        _guarded('requests', requests.pending_tick)
        _guarded('invites', requests.invite_tick)
        if time.time() >= state.get('_drafts_retry', 0):
            with lock:
                if not _guarded('drafts', drafts.tick):  # e.g. a missing scope: retry in 5 min
                    state['_drafts_retry'] = time.time() + 300
        save()
        _guarded('publish', publish.tick)


def run():
    for d in (DATA, FILES, drafts.DRAFTS, outbox.OUTBOX):
        os.makedirs(d, exist_ok=True)
    prepare_for_start()
    polls.migrate()
    log(f'{NAME} for {AGENT}: owner {OWNER}, bridge {BRIDGE}, {len(state["tasks"])} known threads, mode {mode()}')
    slack.WORKSPACE = slack.app.client.auth_test()['url']  # also verifies the bot token: a bad one stops here
    COMP.event('live', f'{NAME} started', detail=f'mode: {mode()}')
    threading.Thread(target=poll, daemon=True).start()
    publish.handler = SocketModeHandler(slack.app, secret('app-token.txt'))
    publish.handler.start()
