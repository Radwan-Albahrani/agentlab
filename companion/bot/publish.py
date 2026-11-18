"""Writes what the hub shows (see companion.py): heartbeat, task cards, open pull requests."""

import re
import threading
import time

from . import ledger, machine, polls, reviews, slack
from .config import COMP, MODES, OWNER, mode
from .state import lock, review_of, state

_last = 0.0
_writing = threading.Lock()
_mode = None
handler = None  # Socket Mode handler, set by main


STATUS = {  # the hub's coarse status of each phase (machine.PHASES)
    'working': 'working',
    'waiting_owner': 'waiting',
    'waiting_answer': 'waiting',
    'paused': 'paused',
    'answered': 'done',
    'nothing_to_do': 'done',
    'stopped': 'stopped',
    'failed': 'failed',
}


def _waiting(t):
    """What the owner is asked for: the first item waiting on them, else an answer to the agent's question."""
    first = next(iter(ledger.pending(t)), None)
    if first:
        if first['kind'] == 'approval':
            return 'approval'
        if first['kind'] == 'credential':
            return 'login'
        return 'send' if first.get('to') == 'requester' else 'post'
    return 'answer' if t.get('phase') == 'waiting_answer' else ''


def card(k, t):
    phase = t.get('phase') or machine.phase_of(t)
    poll = state['polls'].get(t.get('poll') or '')
    status = STATUS[phase]
    if status in ('done',) and poll and poll['open']:
        status = 'working'
    closed = re.sub(r':[a-z_]+:\s*', '', t.get('closed') or '')
    outcome = 'Paused for the usage limit' if phase == 'paused' else closed or machine.outcome(t).replace('_', ' ')
    p = machine.party(t)
    a = t.get('audit') or {}
    by = a.get('by') or ''
    asked_by = review_of(t).get('asked_by') or []
    if asked_by:
        requester = ', '.join(slack.name(u) for u in asked_by)
    else:
        requester = slack.name(p['user']) if p['kind'] != 'owner' else ''
    c = t.get('case') or {}
    return {
        'id': k,
        'title': t.get('title') or '',
        'kind': 'errand' if p['kind'] == 'errand' else 'review' if review_of(t) else 'task',
        'requester': requester,
        'status': status,
        'waiting': _waiting(t) if status == 'waiting' else '',
        'outcome': polls.summary(poll) if poll and poll['open'] else outcome,
        'started': t.get('start') or '',
        'ended': t.get('ended') or '',
        'thread': t.get('thread') or '',
        'slack': slack.link(t.get('channel'), t.get('thread_ts')),
        'source': t.get('source') or '',
        'resumes_at': (t.get('paused') or {}).get('resumes_at') or '' if phase == 'paused' else '',
        'started_by': slack.name(by) if by and by != OWNER else '',
        'via': a.get('via') or '',
        'approved_by': slack.name(a['approved_by']) if a.get('approved_by') else '',
        'party': p['kind'],
        'phase': phase,
        'case_link': slack.link(c['ch'], c['ts']) if c else '',
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
    shown = {c['id'] for c in cards[:300]}
    ledger.publish([t for k, t in state['tasks'].items() if k in shown])
    COMP.polls([polls.card(p) for p in state['polls'].values()])
    COMP.pulls(reviews.rows(card))
