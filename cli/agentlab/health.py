"""Whether each agent is actually up: its container's own health check (Accounts, terminal and T3 answer), not just
"running". A first start downloads the agent's tools, so apply waits for it, and says which agent isn't ready and why
instead of reporting ok while one is still stuck (#18)."""

import json
import time

from . import deploy
from .util import Failed, run, say

READY_S = 20 * 60  # a first start installs Claude Code, Codex and T3 into the agent's home


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
    if st.get('Status') != 'running':
        return 'exited', f'{st.get("Status", "unknown")} (exit {st.get("ExitCode", "?")})'
    health = st.get('Health') or {}
    log = health.get('Log') or []
    detail = ' '.join(str(log[-1].get('Output', '')).split())[-300:] if log else ''
    return health.get('Status') or 'healthy', detail


def wait_ready(cfg, timeout_s=READY_S, sleep=time.sleep, clock=time.time):
    """Until every agent is healthy. Progress once a minute; fails naming each agent that isn't, and why."""
    deadline, said = clock() + timeout_s, None
    while True:
        states = {a['id']: state(cfg, a) for a in cfg['agents']}
        waiting = {aid: s for aid, s in states.items() if s[0] != 'healthy'}
        if not waiting:
            return
        # unhealthy can still recover (a slow first start outlasts the health check's grace period); gone can't
        stuck = {aid: s for aid, s in waiting.items() if s[0] in ('exited', 'missing')}
        if stuck or clock() >= deadline:
            break
        if said is None or clock() - said >= 60:
            say(f'  waiting for {", ".join(sorted(waiting))} to finish starting (a first start downloads their tools)')
            said = clock()
        sleep(10)
    lines = [f'{aid}: {s}' + (f' ({detail})' if detail else '') for aid, (s, detail) in sorted(waiting.items())]
    raise Failed(
        'not every agent is ready: '
        + '; '.join(lines)
        + '. Its log: docker logs <agent container>; a first start stuck on a download recovers with a restart'
    )


def checks(cfg, c):
    """For doctor: a starting agent is a warning (first starts take minutes), a stuck one an error."""
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
