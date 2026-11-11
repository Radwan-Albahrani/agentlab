"""The hub's agent management: jobs/queue/<id>.json from the admin, each run by agentctl in its own systemd unit (so a
watcher restart mid-apply never cuts it off), its output in jobs/<id>.log and its state in jobs/<id>.json."""

import contextlib
import json
import os
import re
import time

from . import host, store
from .settings import AGENTCTL

ID = re.compile(r'^[a-z][a-z0-9-]{0,30}[a-z0-9]$|^[a-z]$')
EMAIL = re.compile(r'^[^@\s/]+@[^@\s/]+\.[^@\s/]+$')
SIZE = re.compile(r'^\d+(\.\d+)?[kmgt]?b?$', re.IGNORECASE)
RESERVE = re.compile(r'^(\d{1,2}%|\d+(\.\d+)?[kmgt]?b?)$', re.IGNORECASE)
CPUS = re.compile(r'^\d{1,3}(\.\d{1,2})?$')
JOB = re.compile(r'^\d{10}-[0-9a-f]{8}$')
KEEP_JOBS = 40
LOST_AFTER_S = 15  # a unit gone with no exit code
RUN_AND_KEEP_EXIT = '"$@"; echo $? > "$0"'  # sh -c: run agentctl, then write its exit code to the file in $0


def _memory(v):
    v = str(v).strip().lower()
    return v if v == 'default' or SIZE.match(v) else None


def _cpus(v):
    v = str(v).strip().lower()
    return v if v == 'default' or (CPUS.match(v) and float(v) > 0) else None


def _limits(args):
    out = []
    for key, flag, check in (('memory', '--memory', _memory), ('cpus', '--cpus', _cpus)):
        if args.get(key) not in (None, ''):
            value = check(args[key])
            if value is None:
                raise ValueError(f'{key} {args[key]!r} is not valid')
            out += [flag, value]
    return out


def _agent_id(args):
    aid = str(args.get('id', ''))
    if not ID.match(aid):
        raise ValueError('agent names are lowercase letters, digits and dashes')
    return aid


def command(op, args):
    """(agentctl arguments, title) for a job; ValueError for anything not allowed."""
    if op == 'agent.add':
        aid, email = _agent_id(args), str(args.get('email', '')).strip().lower()
        if not EMAIL.match(email):
            raise ValueError(f'{email!r} is not an email address')
        return ['agent', 'add', aid, email, *_limits(args)], f'Add {aid} for {email}'
    if op == 'agent.set':
        aid, limits = _agent_id(args), _limits(args)
        if not limits:
            raise ValueError('nothing to change')
        return ['agent', 'set', aid, *limits], f'Resize {aid}'
    if op == 'agent.remove':
        aid = _agent_id(args)
        if args.get('delete_data') is True:
            return ['agent', 'remove', aid, '--yes'], f'Remove {aid} and delete its files'
        return ['agent', 'remove', aid, '--keep-data'], f'Remove {aid} (files kept)'
    if op == 'storage.set':
        out = []
        size = str(args.get('person_size') or '').strip().lower()
        if size:
            if size != 'auto' and not SIZE.match(size):
                raise ValueError(f'disk size {size!r} is not valid')
            out += ['--person-size', size]
        reserve = str(args.get('host_reserve') or '').strip().lower()
        if reserve:
            if not RESERVE.match(reserve):
                raise ValueError(f'host reserve {reserve!r} is not valid')
            out += ['--host-reserve', reserve]
        if not out:
            raise ValueError('nothing to change')
        return ['storage', 'set', *out], 'Change disk sizes'
    raise ValueError(f'unknown job {op!r}')


def _unit(job_id):
    return f'agentlab-job-{job_id}'


def _save(job):
    store.dump(f'jobs/{job["id"]}.json', job)


def start(job):
    try:
        argv, job['title'] = command(job.get('op'), job.get('args') or {})
    except ValueError as e:
        job.update(state='failed', ok=False, message=str(e), started=time.time(), finished=time.time())
        _save(job)
        return
    log, rc = store.path('jobs', f'{job["id"]}.log'), store.path('jobs', f'{job["id"]}.rc')
    with open(log, 'w') as f:
        f.write(f'$ agentctl {" ".join(argv)}\n')
    cmd = [
        'systemd-run',
        '--unit',
        _unit(job['id']),
        '--collect',
        '--setenv=PYTHONUNBUFFERED=1',
        '-p',
        f'StandardOutput=append:{log}',
        '-p',
        f'StandardError=append:{log}',
        '/bin/sh',
        '-c',
        RUN_AND_KEEP_EXIT,
        rc,
        'python3',
        AGENTCTL,
        *argv,
    ]
    code, out = host.run(cmd)
    job.update(state='running' if code == 0 else 'failed', started=time.time())
    if code:
        job.update(ok=False, message=f'could not start: {out[-300:]}', finished=time.time())
    _save(job)


def _summary(log_path, ok):
    """The line worth showing: agentctl's error, else its last warning, else 'Done.'."""
    try:
        with open(log_path) as f:
            lines = [ln.strip() for ln in f.read().splitlines() if ln.strip()]
    except OSError:
        return ''
    for ln in reversed(lines):
        if ln.startswith(('error: ', 'needs action: ')):
            return ln.split(': ', 1)[1]
    if ok:
        warned = [ln[2:] for ln in lines if ln.startswith('! ')]
        return warned[-1] if warned else 'Done.'
    return lines[-1] if lines else ''


def follow(job):
    rc_path, log = store.path('jobs', f'{job["id"]}.rc'), store.path('jobs', f'{job["id"]}.log')
    if os.path.exists(rc_path):
        with open(rc_path) as f:
            ok = f.read().strip() == '0'
        os.remove(rc_path)
        message = _summary(log, ok)
    elif host.unit_active(_unit(job['id'])) or time.time() - job.get('started', 0) < LOST_AFTER_S:
        return
    else:
        ok, message = False, 'stopped without an exit code (did the host restart?); check the log, then try again'
    job.update(state='done' if ok else 'failed', ok=ok, finished=time.time(), message=message)
    _save(job)
    store.event('agents', job['title'] + (' done' if ok else ' failed'), message[:300], ok=ok)


def jobs():
    folder = store.path('jobs')
    out = []
    for name in os.listdir(folder) if os.path.isdir(folder) else []:
        if name.endswith('.json') and JOB.match(name[:-5]):
            j = store.load(f'jobs/{name}', None)
            if isinstance(j, dict):
                out.append(j)
    return sorted(out, key=lambda j: j['id'])


def _prune(finished):
    for j in finished[:-KEEP_JOBS]:
        for ext in ('json', 'log'):
            with contextlib.suppress(OSError):
                os.remove(store.path('jobs', f'{j["id"]}.{ext}'))


def tick():
    """One job at a time, oldest first (agentctl also waits for any other change, such as the nightly update)."""
    queue = store.path('jobs', 'queue')
    os.makedirs(queue, exist_ok=True)
    for j in jobs():
        if j.get('state') == 'running':
            follow(j)
    if any(j.get('state') == 'running' for j in jobs()):
        return
    for name in sorted(os.listdir(queue)):
        path = os.path.join(queue, name)
        try:
            with open(path) as f:
                job = json.load(f)
        except (OSError, ValueError):
            job = None
        os.remove(path)
        if isinstance(job, dict) and JOB.match(str(job.get('id', ''))):
            start(
                {
                    'id': job['id'],
                    'op': str(job.get('op', '')),
                    'args': job.get('args') or {},
                    'by': job.get('by', ''),
                    'queued': job.get('queued', time.time()),
                    'title': str(job.get('op', '')),
                }
            )
            break
    _prune([j for j in jobs() if j.get('state') in ('done', 'failed')])
