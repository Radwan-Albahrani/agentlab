"""Nightly backups of agents' T3 and companion databases, hub state and config, via SQLite's online backup API."""

import contextlib
import datetime
import os
import shutil
import sqlite3
import time
from typing import TypedDict

from . import config, deploy
from .config import Cluster
from .util import AGENT_UID, Failed, Needs, Plan, need_root, say

DB_SUFFIXES = ('.sqlite', '.sqlite3', '.db')


class Done(TypedDict):
    """What `backup run` reports."""

    date: str
    databases: int
    pruned: list[str]


class Backup(TypedDict):
    """One day's backup, as `backup list` reports it."""

    date: str
    bytes: int
    agents: list[str]


class Restored(TypedDict):
    restored: list[str]


def root(cfg: Cluster) -> str:
    return f'{cfg["data"]}/backups'


def databases(base: str) -> list[str]:
    out: list[str] = []
    for folder, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in ('node_modules', '.git', 'cache', 'Cache')]
        # an empty file holds no data; T3's server-owner.sqlite is one, write-locked while t3 serve runs
        out += [
            os.path.relpath(os.path.join(folder, f), base)
            for f in files
            if f.endswith(DB_SUFFIXES) and os.path.getsize(os.path.join(folder, f)) > 0
        ]
    return sorted(out)


def t3_root(cfg: Cluster, agent_id: str) -> str:
    return f'{config.agent(cfg, agent_id)["path"]}/home/.t3'


BUSY_S = 30  # how long a locked database may hold up its copy before it's reported as failed


def copy_db(src: str, dst: str) -> None:
    """A consistent copy of `src` at `dst` (SQLite's online backup, all pages in one step), or sqlite3.Error."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + '.tmp'
    if os.path.exists(tmp):
        os.remove(tmp)
    give_up = time.monotonic() + BUSY_S

    def progress(status: int, remaining: int, total: int) -> None:
        # backup() retries a locked source forever; it calls this after every step, busy ones too, and stops on a raise
        if status in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) and time.monotonic() >= give_up:
            raise sqlite3.OperationalError(f'database is locked (gave up after {BUSY_S} s)')

    source = sqlite3.connect(src, timeout=BUSY_S)
    try:
        with contextlib.closing(sqlite3.connect(tmp)) as target:
            source.backup(target, progress=progress)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise
    finally:
        source.close()
    os.replace(tmp, dst)


def run(cfg: Cluster, config_path: str, today: datetime.date | None = None) -> Done:
    need_root('agentctl backup run')
    day = (today or datetime.date.today()).isoformat()
    dest = f'{root(cfg)}/{day}'
    os.makedirs(dest, mode=0o700, exist_ok=True)
    copied = 0
    failed: list[str] = []
    sources = [(f'agents/{a["id"]}', t3_root(cfg, a['id'])) for a in cfg['agents']]
    sources += [(f'companions/{c["name"]}', f'{cfg["data"]}/companions/{c["name"]}') for c in cfg['companions']]
    for name, base in sources:
        for rel in databases(base) if os.path.isdir(base) else []:
            try:
                copy_db(os.path.join(base, rel), os.path.join(dest, name, rel))
                copied += 1
            except sqlite3.Error as e:
                failed.append(f'{name}/{rel}: {e}')
    shutil.copy2(config_path, f'{dest}/cluster.toml')
    hub_state = f'{cfg["data"]}/hub/data'
    if os.path.isdir(hub_state):
        shutil.copytree(hub_state, f'{dest}/hub', dirs_exist_ok=True)
    pruned = prune(cfg, today)
    say(
        f'backup {day}: {copied} databases'
        + (f', {len(failed)} failed' if failed else '')
        + (f', removed {", ".join(pruned)}' if pruned else '')
    )
    if failed:
        raise Failed('some databases could not be backed up:\n  ' + '\n  '.join(failed))
    return {'date': day, 'databases': copied, 'pruned': pruned}


def prune(cfg: Cluster, today: datetime.date | None = None) -> list[str]:
    keep = cfg['backups']['keep_days']
    oldest = (today or datetime.date.today()) - datetime.timedelta(days=keep - 1)
    gone: list[str] = []
    for name in sorted(os.listdir(root(cfg))) if os.path.isdir(root(cfg)) else []:
        try:
            day = datetime.date.fromisoformat(name)
        except ValueError:
            continue
        if day < oldest:
            shutil.rmtree(os.path.join(root(cfg), name))
            gone.append(name)
    return gone


def listing(cfg: Cluster) -> list[Backup]:
    rows: list[Backup] = []
    for name in sorted(os.listdir(root(cfg))) if os.path.isdir(root(cfg)) else []:
        folder = os.path.join(root(cfg), name)
        size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(folder) for f in fs)
        agents = sorted(os.listdir(os.path.join(folder, 'agents'))) if os.path.isdir(f'{folder}/agents') else []
        rows.append({'date': name, 'bytes': size, 'agents': agents})
        say(f'  {name}  {size / 2**20:8.1f} MiB  {", ".join(agents)}')
    return rows


def restore(cfg: Cluster, day: str, agent_id: str, yes: bool = False) -> Restored:
    """Put one agent's T3 databases back as they were on `day`; the agent is stopped while they are swapped."""
    src = f'{root(cfg)}/{day}/agents/{agent_id}'
    if not os.path.isdir(src):
        raise Failed(f'no backup of {agent_id} on {day} (agentctl backup list)')
    target = t3_root(cfg, agent_id)
    dbs = databases(src)
    stack = f'agentlab-agent-{agent_id}'
    lines = (
        [f'stop {stack}']
        + [f'REPLACE {target}/{rel} with the {day} copy (newer chats in it are lost)' for rel in dbs]
        + [f'start {stack}']
    )
    for line in lines:
        say(f'  {line}')
    if not yes:
        raise Needs("restoring overwrites the agent's current chats: re-run with --yes")
    need_root('agentctl backup restore')
    plan = Plan(False)
    deploy.stop(cfg, stack, plan)
    for rel in dbs:
        dst = os.path.join(target, rel)
        for sidecar in ('-wal', '-shm', '-journal'):
            if os.path.exists(dst + sidecar):
                os.remove(dst + sidecar)  # a stale WAL would be replayed onto the restored file
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(src, rel), dst)
        os.chown(dst, AGENT_UID, AGENT_UID)
    deploy.start(cfg, stack, plan)
    return {'restored': dbs}
