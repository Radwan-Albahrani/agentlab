"""Host broker of the agents' heavy-job throttle (systemd unit agentlab-throttle). Many agents run at once and their
installs, builds and test runs would otherwise all start together, blow up RAM and fill swap. Each heavy job waits
here until both its agent (its mem_limit) and the shared pool (agentlab.slice, limits.total_memory) have room for its
learned peak and the disk isn't congested, then runs; the agents never notice more than a slower command. Runs as
`python3 -m throttle` from host/. Tuning: settings.py; budgets come from cluster.json."""

import sys
import time

from . import facts, scheduler, spool
from .peaks import Peaks
from .settings import POLL_S, STALE_S


class Broker:
    def __init__(self):
        self.peaks = Peaks()
        self.last_start = 0.0

    def tick(self):
        folders = spool.agents()
        jobs = []
        for agent, folder in list(folders.items()):
            try:
                spool.prepare(folder)
                self.learn(folder)
                jobs += self.live_jobs(agent, folder)
            except (OSError, ValueError) as e:  # one agent's broken spool (say, a symlink) mustn't stop the others
                print(f'{agent}: spool skipped: {type(e).__name__}: {e}', file=sys.stderr, flush=True)
                del folders[agent]
        agents = {agent: facts.agent_mb(agent) for agent in folders}
        for job in scheduler.to_admit(
            jobs, facts.pool_mb(), agents, facts.swap_used_mb(), facts.io_pressure(), time.time() - self.last_start
        ):
            spool.admit(folders[job.agent], job)
            job.admitted = True
            self.last_start = time.time()
        for agent, folder in folders.items():
            spool.publish_status(folder, [j for j in jobs if j.agent == agent])

    def learn(self, folder):
        for signature, peak_mb in spool.finished(folder):
            if peak_mb:
                self.peaks.record(signature, peak_mb)

    def live_jobs(self, agent, folder):
        """The agent's queued and running jobs, with their estimates; jobs whose shim went silent are dropped."""
        out = []
        for job in spool.jobs(agent, folder):
            if time.time() - job.seen > STALE_S:
                spool.forget(folder, job)
                continue
            job.estimate_mb = self.peaks.estimate_mb(job.signature, job.tool)
            job.known = self.peaks.known(job.signature)
            out.append(job)
        return out


def main():
    broker = Broker()
    while True:
        try:
            broker.tick()
        except Exception as e:  # keep serving; one bad file mustn't stop the gate
            print(f'tick failed: {type(e).__name__}: {e}', file=sys.stderr, flush=True)
        time.sleep(POLL_S)
