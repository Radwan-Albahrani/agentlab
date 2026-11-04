"""Which queued heavy jobs may start now; with nothing running, the next job always starts."""

from .settings import ADMIT_GAP_S, AGENT_HEADROOM_MB, IO_PRESSURE_MAX, POOL_HEADROOM_MB, SWAP_CAP_MB


def to_admit(jobs, pool, agents, swap_mb, io_pressure, since_last_start_s):
    """pool: (used, limit) MB; agents: {agent: (used, limit) or None}; returns the jobs to start now."""
    running = [j for j in jobs if j.admitted]
    if running and (io_pressure > IO_PRESSURE_MAX or since_last_start_s < ADMIT_GAP_S):
        return []
    free = _free_room(running, pool, agents)
    measuring = {j.signature for j in running if not j.known}
    held_agents = set()
    admitted = []
    for job in _fair_order([j for j in jobs if not j.admitted], running):
        if job.agent in held_agents or (not job.known and job.signature in measuring):
            continue
        idle = not running and not admitted
        if admitted:
            break  # one start at a time; the next waits out ADMIT_GAP_S
        if not idle and swap_mb > SWAP_CAP_MB:
            break
        if not idle and job.estimate_mb > free['pool']:
            break
        if not idle and job.estimate_mb > free.get(job.agent, 0):
            held_agents.add(job.agent)
            continue
        admitted.append(job)
        free['pool'] -= job.estimate_mb
        free[job.agent] = free.get(job.agent, 0) - job.estimate_mb
        if not job.known:
            measuring.add(job.signature)
    return admitted


def _still_to_use(jobs):
    return sum(max(0, j.estimate_mb - j.rss_mb) for j in jobs)


def _free_room(running, pool, agents):
    free = {'pool': pool[1] - POOL_HEADROOM_MB - pool[0] - _still_to_use(running)}
    for agent, usage in agents.items():
        if usage:
            free[agent] = (
                usage[1] - AGENT_HEADROOM_MB - usage[0] - _still_to_use(j for j in running if j.agent == agent)
            )
    return free


def _fair_order(queued, running):
    load = {}
    for j in running:
        load[j.agent] = load.get(j.agent, 0) + 1
    order, waiting = [], sorted(queued, key=lambda j: j.created)
    while waiting:
        nxt = min(waiting, key=lambda j: (load.get(j.agent, 0), j.created))
        order.append(nxt)
        waiting.remove(nxt)
        load[nxt.agent] = load.get(nxt.agent, 0) + 1
    return order
