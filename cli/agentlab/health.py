"""Agent readiness: each container's own health check, not just "running"."""

import json
import time

from . import deploy
from .util import Failed, run, say

READY_S = 20 * 60
MISSING_GRACE_S = 120  # a Coolify rollout removes the old container before it creates the new one


def state(cfg, agent):
    """(state, detail): healthy, starting, unhealthy, exited or missing; detail is the last health-check output."""
    ids = deploy.containers(cfg, f'agentlab-agent-{agent["id"]}', 'agent', all_states=True)
    if not ids:
        return 'missing', 'no container'
    rc, out = run(['docker', 'inspect', '-f', '{{json .State}}', ids[0]], check=False)
    try:
        st = json.loads(out) if rc == 0 else {}
    except ValueError:
        st = {}
    status, error = st.get('Status'), ' '.join(str(st.get('Error') or '').split())[-300:]
    if status in ('created', 'restarting') and not error:
        return 'starting', f'{status} (Coolify or Docker is still bringing it up)'
    if status != 'running':
        return 'exited', error or f'{status or "unknown"} (exit {st.get("ExitCode", "?")})'
    health = st.get('Health') or {}
    log = health.get('Log') or []
    detail = ' '.join(str(log[-1].get('Output', '')).split())[-300:] if log else ''
    return health.get('Status') or 'healthy', detail


def wait_ready(cfg, timeout_s=READY_S, sleep=time.sleep, clock=time.time):
    """Until every agent is healthy; fails naming each agent that isn't, and why."""
    start = clock()
    deadline, said = start + timeout_s, None
    while True:
        states = {a['id']: state(cfg, a) for a in cfg['agents']}
        waiting = {aid: s for aid, s in states.items() if s[0] != 'healthy'}
        if not waiting:
            return
        rolled = clock() - start >= MISSING_GRACE_S
        stuck = {aid: s for aid, s in waiting.items() if s[0] == 'exited' or (s[0] == 'missing' and rolled)}
        if stuck or clock() >= deadline:
            break
        if said is None or clock() - said >= 60:
            say(f'  waiting for {", ".join(sorted(waiting))} to finish starting (a first start downloads their tools)')
            said = clock()
        sleep(10)
    lines = [f'{aid}: {s}' + (f' ({detail})' if detail else '') for aid, (s, detail) in sorted(waiting.items())]
    hint = (
        'a first start stuck on a download recovers with a restart'
        if all(s == 'unhealthy' for s, _ in waiting.values())
        else 'see docker logs <agent container> and the error above'
    )
    raise Failed('not every agent is ready: ' + '; '.join(lines) + f'. {hint}')


def core_state(cfg, service):
    """(state, detail) of one agentlab-core service."""
    ids = deploy.containers(cfg, 'agentlab-core', service, all_states=True)
    if not ids:
        return 'missing', 'no container'
    rc, out = run(['docker', 'inspect', '-f', '{{json .State}}', ids[0]], check=False)
    try:
        st = json.loads(out) if rc == 0 else {}
    except ValueError:
        st = {}
    if st.get('Status') != 'running' or st.get('Restarting'):
        status = 'restarting' if st.get('Restarting') else st.get('Status', 'unknown')
        return status, ' '.join(str(st.get('Error') or f'exit {st.get("ExitCode", "?")}').split())[-300:]
    health = (st.get('Health') or {}).get('Status')
    return health or 'running', ''


def core_checks(cfg, c):
    from . import render  # noqa: PLC0415 - render imports this module's neighbours

    for service in render.core(cfg)['services']:
        s, detail = core_state(cfg, service)
        ok = s in ('running', 'healthy')
        c.add(
            f'core-{service}',
            ok,
            f'core {service} {s}' + (f': {detail}' if detail else ''),
            'agentctl apply; if it stays down, docker logs on it',
            'warning' if s == 'starting' else 'error',
        )


def checks(cfg, c):
    for a in cfg['agents']:
        s, detail = state(cfg, a)
        if s == 'healthy':
            c.add(f'agent-health-{a["id"]}', True, f'{a["id"]} healthy')
        elif s == 'starting':
            c.add(
                f'agent-health-{a["id"]}',
                False,
                f'{a["id"]} still starting (a first start downloads its tools)',
                'wait a few minutes; if it stays starting, see its log (docker logs) and restart it',
                'warning',
            )
        else:
            c.add(
                f'agent-health-{a["id"]}',
                False,
                f'{a["id"]} {s}' + (f': {detail}' if detail else ''),
                'see its log (docker logs), then agentctl apply',
            )
