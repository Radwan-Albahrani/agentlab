"""File handshake with the agent's shim (.job -> .go -> .run -> .done); agent-owned, so only via safe.Folder."""

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
    seen: float
    admitted: bool
    rss_mb: int = 0
    estimate_mb: int = 0
    known: bool = False  # a measured peak exists for this signature


def homes():
    """{agent id: home}; re-reads cluster.json each call so new agents join without a restart."""
    return {a['id']: os.path.join(a['path'], 'home') for a in cluster.load().get('agents') or [] if a.get('path')}


def agents():
    return {aid: home for aid, home in homes().items() if os.path.isdir(home)}


def folder(home):
    return Folder(home, SPOOL, create=True)


def prepare(home):
    with folder(home) as f:
        f.write_json('settings.json', {'max_wait_s': MAX_WAIT_S})
        f.write_json('broker.alive', {'at': time.time()})


def jobs(agent, home):
    """A job counts as running once admitted or started on its own after the max wait."""
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
    """[(signature, peak_mb or None)] of ended jobs; consumes their records."""
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
    ordered = sorted(agent_jobs, key=lambda j: j.created)
    with folder(home) as f:
        f.write_json(
            'status.json',
            {
                'running': [j.label for j in ordered if j.admitted],
                'waiting': [j.label for j in ordered if not j.admitted],
            },
        )
