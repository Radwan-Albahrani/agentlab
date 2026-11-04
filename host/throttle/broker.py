"""Host broker that admits agents' heavy jobs once their agent and the shared pool have room."""

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
            except (OSError, ValueError) as e:  # one agent's broken spool mustn't stop the others
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
        except Exception as e:  # keep serving
            print(f'tick failed: {type(e).__name__}: {e}', file=sys.stderr, flush=True)
        time.sleep(POLL_S)
