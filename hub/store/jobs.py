"""Agent management jobs: the hub queues them for the host watcher (host/watch/jobs.py) and reads back their state
and log."""

import json
import os
import secrets
import time

from .files import read_json
from .watch import WATCH

LOG_TAIL = 64 * 1024


def _dir(*parts):
    return os.path.join(WATCH, 'jobs', *parts)


def submit(op, args, by):
    """Queue a job; -> its id. The watcher validates it again before anything runs."""
    job_id = f'{int(time.time())}-{secrets.token_hex(4)}'
    os.makedirs(_dir('queue'), exist_ok=True)
    tmp = _dir('queue', f'.{job_id}.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'id': job_id, 'op': op, 'args': args, 'by': by, 'queued': time.time()}, f)
    os.replace(tmp, _dir('queue', f'{job_id}.json'))
    return job_id


def queued():
    out = []
    folder = _dir('queue')
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if name.endswith('.json') and not name.startswith('.'):
            j = read_json(os.path.join(folder, name), None)
            if isinstance(j, dict):
                out.append({**j, 'state': 'queued'})
    return out


def recent(limit=15):
    """Newest first: queued, then running and finished."""
    folder = _dir()
    done = []
    for name in os.listdir(folder) if os.path.isdir(folder) else []:
        if name.endswith('.json'):
            j = read_json(os.path.join(folder, name), None)
            if isinstance(j, dict) and j.get('id'):
                done.append(j)
    return (queued()[::-1] + sorted(done, key=lambda j: j['id'], reverse=True))[:limit]


def log(job_id):
    if not job_id.replace('-', '').isalnum():
        return ''
    try:
        with open(_dir(f'{job_id}.log'), 'rb') as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - LOG_TAIL))
            return f.read().decode('utf-8', 'replace')
    except OSError:
        return ''
