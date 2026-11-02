"""The file handshake between an agent's shim and the host broker, in a folder of the agent's home.
No network service: the shim drops <id>.job, the broker answers <id>.go, the running job keeps <id>.run fresh,
and <id>.done carries the measured peak back. pid-<n> marks a running job's process, so commands it starts aren't
gated twice. The broker also leaves broker.alive, settings.json and status.json. The folder belongs to the agent,
so the broker (root) touches it only through safe.Folder: no symlink or FIFO there can redirect it."""

import os
import time
from dataclasses import dataclass

import cluster
from safe import Folder

from .settings import MAX_WAIT_S, SPOOL


@dataclass
class Job:
    agent: str
    id: str
    signature: str
    tool: str
    label: str
    created: float
    seen: float  # last sign of life from the shim
    admitted: bool
    rss_mb: int = 0
    estimate_mb: int = 0
    known: bool = False  # a measured peak exists for this signature


def homes():
    """{agent id: its home on the host}, from cluster.json (re-read each call, so new agents join without a restart)."""
    return {a['id']: os.path.join(a['path'], 'home') for a in cluster.load().get('agents') or [] if a.get('path')}


def agents():
    """{agent id: its home} for every agent whose home exists."""
    return {aid: home for aid, home in homes().items() if os.path.isdir(home)}


def folder(home):
    return Folder(home, SPOOL, create=True)


def prepare(home):
    """Make sure the folder exists for the shim and tell it the broker is up and how long it may wait."""
    with folder(home) as f:
        f.write_json('settings.json', {'max_wait_s': MAX_WAIT_S})
        f.write_json('broker.alive', {'at': time.time()})


def jobs(agent, home):
    """The agent's jobs; one is running once it was let in or has started on its own after the max wait."""
    out = []
    with folder(home) as f:
        for name in f.names('.job'):
            meta = f.read_json(name)
            if not isinstance(meta, dict) or not {'signature', 'tool', 'label', 'created'} <= meta.keys():
                continue
            jid = name[:-4]
            run = f.read_json(jid + '.run')
            seen = max(f.mtime(name), f.mtime(jid + '.run') if run else 0)
            running = run is not None or f.exists(jid + '.go')
            out.append(
                Job(
                    agent,
                    jid,
                    str(meta['signature']),
                    str(meta['tool']),
                    str(meta['label']),
                    float(meta['created']),
                    seen,
                    admitted=running,
                    rss_mb=int((run or {}).get('rss_mb', 0) or 0) if isinstance(run, dict) else 0,
                )
            )
    return out


def finished(home):
    """[(signature, peak_mb or None)] of jobs that ended since the last look; their records are consumed."""
    out = []
    with folder(home) as f:
        for name in f.names('.done'):
            record = f.read_json(name)
            f.remove(name)
            if isinstance(record, dict) and record.get('signature'):
                peak = record.get('peak_mb')
                out.append((str(record['signature']), int(peak) if isinstance(peak, int | float) else None))
    return out


def admit(home, job):
    with folder(home) as f:
        f.write_json(job.id + '.go', {'estimate_mb': job.estimate_mb})


def forget(home, job):
    with folder(home) as f:
        for ext in ('.job', '.go', '.run'):
            f.remove(job.id + ext)


def publish_status(home, agent_jobs):
    """What the hub shows for this agent: admitted jobs and queued ones, oldest first."""
    ordered = sorted(agent_jobs, key=lambda j: j.created)
    with folder(home) as f:
        f.write_json(
            'status.json',
            {
                'running': [j.label for j in ordered if j.admitted],
                'waiting': [j.label for j in ordered if not j.admitted],
            },
        )
