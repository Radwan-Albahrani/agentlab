"""What the hub shows about the companion (see companion.py): a heartbeat, every task as a small card, and the
open pull requests its GitHub App sees, each with its latest review."""

import re
import time

from . import polls, reviews, slack
from .config import COMP, MODES, mode
from .state import state

_last = 0.0
_mode = None
handler = None  # the Socket Mode connection, set by main


def card(k, t):
    a = t.get('approval') or {}
    waiting = (
        'approval'
        if a and not a.get('decided')
        else 'send'
        if t.get('reply_draft')
        else 'post'
        if t.get('post_draft')
        else 'login'
        if t.get('cred_ask')
        else 'answer'
        if t.get('question')
        else ''
    )
    closed = re.sub(r':[a-z_]+:\s*', '', t.get('closed') or '')
    outcome = t.get('outcome') or ''
    poll = state['polls'].get(t.get('poll') or '')
    if waiting:
        status = 'waiting'
    elif t.get('active') or (poll and poll['open']):
        status = 'working'
    elif outcome == 'stopped' or closed.startswith(('Stopped', 'Rejected')):
        status = 'stopped'
    elif outcome == 'failed':
        status = 'failed'
    else:
        status = 'done'
    req = t.get('requester')
    return {
        'id': k,
        'title': t.get('title') or '',
        'kind': 'errand' if req else 'review' if t.get('review') else 'task',
        'requester': slack.name(req) if req else '',
        'status': status,
        'waiting': waiting,
        'outcome': polls.summary(poll) if poll and poll['open'] else closed or outcome,
        'started': t.get('start') or '',
        'ended': t.get('ended') or '',
        'thread': t.get('thread') or '',
        'slack': slack.link(t.get('channel'), t.get('thread_ts')),
        'source': t.get('source') or '',
    }


def tick():
    global _last
    if time.time() - _last < 5:
        return
    _last = time.time()
    try:
        connected = bool(handler and handler.client.is_connected())
    except Exception:
        connected = False
    global _mode
    m = mode()
    if _mode and m != _mode:  # changed on the hub
        label = next((o['label'] for o in MODES if o['value'] == m), m)
        COMP.event('settings', f'Mode is now {label}', detail=f'{_mode} -> {m}')
    _mode = m
    COMP.heartbeat(
        connected=connected,
        mode=m,
        workspace=slack.WORKSPACE,
        channels=slack.channels(),
        github=reviews.heartbeat(),
    )
    cards = sorted((card(k, t) for k, t in state['tasks'].items()), key=lambda c: c['started'], reverse=True)
    COMP.tasks(cards[:300])
    COMP.polls([polls.card(p) for p in state['polls'].values()])
    COMP.pulls(reviews.rows(card))
