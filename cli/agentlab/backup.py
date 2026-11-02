"""Nightly backups of what can't be rebuilt: every agent's T3 databases (their chats), companion databases and the
config. SQLite's online backup API copies a consistent snapshot while T3 keeps writing, which a plain file copy of
a database in WAL mode does not."""

import datetime
import os
import shutil
import sqlite3

from . import config, deploy
from .util import AGENT_UID, Failed, Needs, Plan, need_root, say

DB_SUFFIXES = ('.sqlite', '.sqlite3', '.db')


def root(cfg):
    return f'{cfg["data"]}/backups'


def databases(base):
    """Relative paths of the SQLite databases under base (sidecar -wal / -shm files are not databases)."""
    out = []
    for folder, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in ('node_modules', '.git', 'cache', 'Cache')]
        out += [os.path.relpath(os.path.join(folder, f), base) for f in files if f.endswith(DB_SUFFIXES)]
    return sorted(out)


def t3_root(cfg, agent_id):
    return f'{config.agent(cfg, agent_id)["path"]}/home/.t3'


def copy_db(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    source = sqlite3.connect(src, timeout=30)
    target = sqlite3.connect(dst + '.tmp')
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    os.replace(dst + '.tmp', dst)


def run(cfg, config_path, today=None):
    need_root('agentctl backup run')
    day = (today or datetime.date.today()).isoformat()
    dest = f'{root(cfg)}/{day}'
    os.makedirs(dest, mode=0o700, exist_ok=True)
    copied, failed = 0, []
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
    pruned = prune(cfg, today)
    say(
        f'backup {day}: {copied} databases'
        + (f', {len(failed)} failed' if failed else '')
        + (f', removed {", ".join(pruned)}' if pruned else '')
    )
    if failed:
        raise Failed('some databases could not be backed up:\n  ' + '\n  '.join(failed))
    return {'date': day, 'databases': copied, 'pruned': pruned}


def prune(cfg, today=None):
    keep = cfg['backups']['keep_days']
    oldest = (today or datetime.date.today()) - datetime.timedelta(days=keep - 1)
    gone = []
    for name in sorted(os.listdir(root(cfg))) if os.path.isdir(root(cfg)) else []:
        try:
            day = datetime.date.fromisoformat(name)
        except ValueError:
            continue  # not ours
        if day < oldest:
            shutil.rmtree(os.path.join(root(cfg), name))
            gone.append(name)
    return gone


def listing(cfg):
    rows = []
    for name in sorted(os.listdir(root(cfg))) if os.path.isdir(root(cfg)) else []:
        folder = os.path.join(root(cfg), name)
        size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(folder) for f in fs)
        agents = sorted(os.listdir(os.path.join(folder, 'agents'))) if os.path.isdir(f'{folder}/agents') else []
        rows.append({'date': name, 'bytes': size, 'agents': agents})
        say(f'  {name}  {size / 2**20:8.1f} MiB  {", ".join(agents)}')
    return rows


def restore(cfg, day, agent_id, yes=False):
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
