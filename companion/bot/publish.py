"""Writes what the hub shows (see companion.py): heartbeat, task cards, open pull requests."""

import re
import threading
import time

from . import polls, reviews, slack
from .config import COMP, MODES, OWNER, mode
from .state import lock, review_of, state

_last = 0.0
_writing = threading.Lock()
_mode = None
handler = None  # Socket Mode handler, set by main


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
    paused = t.get('paused') if t.get('active') else None
    if waiting:
        status = 'waiting'
    elif paused:
        status = 'paused'
        outcome = 'Paused for the usage limit'
    elif t.get('active') or (poll and poll['open']):
        status = 'working'
    elif outcome == 'stopped' or closed.startswith(('Stopped', 'Rejected')):
        status = 'stopped'
    elif outcome == 'failed':
        status = 'failed'
    else:
        status = 'done'
    req = t.get('requester')
    a = t.get('audit') or {}
    by = a.get('by') or t.get('guest') or ''  # tasks from before the audit: the guest, else the owner
    asker = req or (by if by != OWNER else '')
    asked_by = review_of(t).get('asked_by') or []
    return {
        'id': k,
        'title': t.get('title') or '',
        'kind': 'errand' if req else 'review' if review_of(t) else 'task',
        'requester': ', '.join(slack.name(u) for u in asked_by) if asked_by else slack.name(asker) if asker else '',
        'status': status,
        'waiting': waiting,
        'outcome': polls.summary(poll) if poll and poll['open'] else closed or outcome,
        'started': t.get('start') or '',
        'ended': t.get('ended') or '',
        'thread': t.get('thread') or '',
        'slack': slack.link(t.get('channel'), t.get('thread_ts')),
        'source': t.get('source') or '',
        'resumes_at': (paused or {}).get('resumes_at') or '',
        'started_by': slack.name(by) if by and by != OWNER else '',
        'via': a.get('via') or '',
        'approved_by': slack.name(a['approved_by']) if a.get('approved_by') else '',
    }


def tick():
    global _last
    if time.time() - _last < 5:
        return
    _last = time.time()
    with _writing:
        _publish()


def now():
    """Publish now instead of on the next beat."""
    global _last
    _last = time.time()
    with lock, _writing:
        _publish()


def _publish():
    try:
        connected = bool(handler and handler.client.is_connected())
    except Exception:
        connected = False
    global _mode
    m = mode()
    if _mode and m != _mode:
        label = next((o['label'] for o in MODES if o['value'] == m), m)
        COMP.event('settings', f'Mode is now {label}', detail=f'{_mode} -> {m}')
    _mode = m
    COMP.heartbeat(
        connected=connected,
        mode=m,
        workspace=slack.WORKSPACE,
        channels=slack.channels(),
        people=slack.colleagues(),
        github=reviews.heartbeat(),
    )
    cards = sorted((card(k, t) for k, t in state['tasks'].items()), key=lambda c: c['started'], reverse=True)
    COMP.tasks(cards[:300])
    COMP.polls([polls.card(p) for p in state['polls'].values()])
    COMP.pulls(reviews.rows(card))
