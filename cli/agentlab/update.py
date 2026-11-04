"""`agentctl update`: agentlab keeping itself current, by hand or nightly (agentlab-update.timer, [updates]).

1. git pull, fast-forward only (local changes or a diverged branch stop it: nothing is merged or thrown away), then
   the rest runs again with the new code.
2. Build (or pull) the images; Docker's cache makes an unchanged image a no-op.
3. `apply`: every stack whose file or image changed is redeployed. The core and companions go straight away; an
   agent in the middle of a T3 turn is not restarted.
4. Busy agents are waited for: checked every few minutes for up to [updates] wait_hours, each updated the moment it is
   idle (an idle agent never waits for a busy one). At the end of the window, on_busy decides: "defer" leaves it for
   the next run, "resume" restarts it anyway and then tells each T3 chat whose turn the restart cut off to carry on.
   `--resume` skips the wait: busy agents are resumed at once (when something waiting on the update can't wait).
5. (inside apply) Each companion checkout gets template changes merged in when it's clean and they don't conflict
   (template.py).

The outcome goes to <data>/state/update.json, which `status` and `doctor` show."""

import datetime
import json
import os
import sqlite3
import sys
import time

from . import apply, deploy, images, render
from .util import REPO, Failed, Plan, load_json, need_root, run, say, warn

CHECK_EVERY_S = 300
CONTINUE = 'The server restarted for an update; continue where you left off.'


def state_path(cfg):
    return os.path.join(cfg['data'], 'state', 'update.json')


def last(cfg):
    return load_json(state_path(cfg), {}) or {}


def record(cfg, **result):
    path = state_path(cfg)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    result['at'] = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    with open(path + '.tmp', 'w') as f:
        json.dump(result, f, indent=2)
    os.replace(path + '.tmp', path)
    return result


# ---------------------------------------------------------------- the code
def git(*args, check=True):
    return run(['git', '-C', REPO, *args], check=check)


def head():
    return git('rev-parse', '--short', 'HEAD')[1].strip()


def pull(branch):
    """Fast-forward the repo to origin/<branch>. -> (from, to)"""
    if git('rev-parse', '--is-inside-work-tree', check=False)[0]:
        raise Failed(f'{REPO} is not a git checkout: clone the repo there (git clone <url> {REPO}) to update it')
    if git('status', '--porcelain', '--untracked-files=no')[1].strip():
        raise Failed(f'{REPO} has local changes: commit or stash them; update never overwrites them')
    before = head()
    git('fetch', '--quiet', 'origin', branch)
    if git('merge-base', '--is-ancestor', 'HEAD', f'origin/{branch}', check=False)[0]:
        raise Failed(f'{REPO} has commits that origin/{branch} does not: it cannot fast-forward, so nothing changed')
    git('merge', '--ff-only', '--quiet', f'origin/{branch}')
    return before, head()


# ---------------------------------------------------------------- agents
def inflight(agent):
    """[(run id, thread id)] of T3 turns in progress, read on the host."""
    db = os.path.join(agent['path'], 'home', '.t3', 'userdata', 'statev2.sqlite')
    try:
        with sqlite3.connect(f'file:{db}?mode=ro', uri=True, timeout=5) as c:
            marks = ','.join('?' * len(deploy.SETTLED))
            q = f'select run_id, thread_id from orchestration_v2_projection_runs where status not in ({marks})'
            return [tuple(r) for r in c.execute(q, deploy.SETTLED)]
    except sqlite3.Error:
        return []


def statuses(agent, run_ids):
    db = os.path.join(agent['path'], 'home', '.t3', 'userdata', 'statev2.sqlite')
    try:
        with sqlite3.connect(f'file:{db}?mode=ro', uri=True, timeout=5) as c:
            marks = ','.join('?' * len(run_ids))
            q = f'select run_id, status from orchestration_v2_projection_runs where run_id in ({marks})'
            return dict(c.execute(q, list(run_ids)).fetchall())
    except sqlite3.Error:
        return {}


def agent_container(cfg, agent):
    ids = deploy.containers(cfg, f'agentlab-agent-{agent["id"]}', 'agent')
    return ids[0] if ids else ''


def wait_healthy(cfg, agent, timeout_s=900, sleep=time.sleep):
    """Until the agent's container reports healthy (T3 answers). -> container id, or '' on timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        cid = agent_container(cfg, agent)
        if (
            cid
            and run(['docker', 'inspect', '-f', '{{.State.Health.Status}}', cid], check=False)[1].strip() == 'healthy'
        ):
            return cid
        sleep(10)
    return ''


def send_continue(cid, thread):
    """Post the continue message to one T3 chat, the way the companion bridge does (`t3 thread send`, text on stdin)."""
    rc, out = run(
        ['docker', 'exec', '-i', '-u', 'agent', '-w', '/workspace', cid, 't3', 'thread', 'send', '--json', thread, '-'],
        check=False,
        input_text=CONTINUE,
    )
    if rc:
        warn(f'could not tell chat {thread} to continue: {out.strip()[:200]}')
    return rc == 0


def resume(cfg, agent, kind, key, plan, sleep=time.sleep):
    """Restart a busy agent anyway, then tell each chat whose turn it cut off to carry on. -> threads told"""
    running = inflight(agent)
    deploy.deploy(cfg, f'agentlab-agent-{agent["id"]}', kind, key, plan, force=True)
    cid = wait_healthy(cfg, agent, sleep=sleep)
    if not cid:
        warn(f'{agent["id"]} did not come back healthy in time; its interrupted chats were not resumed')
        return []
    now = statuses(agent, [r for r, _ in running]) if running else {}
    told = []
    for run_id, thread in running:
        if now.get(run_id) == 'interrupted' and thread not in told and send_continue(cid, thread):
            told.append(thread)
    return told


def pending_agents(cfg):
    """Agents apply left out because a T3 turn was running: a newer image, or a changed file, not live yet."""
    out = []
    for a in cfg['agents']:
        stack = f'agentlab-agent-{a["id"]}'
        path = deploy.compose_file(cfg, stack)
        if not os.path.isfile(path) or deploy.deployed_this_run(stack):  # apply already brought it up to date
            continue
        with open(path) as f:
            text = f.read()
        if deploy.changed_since_deploy(cfg, stack, text) or deploy.stale_images(cfg, stack):
            out.append(a)
    return out


def wait_for_agents(cfg, plan, wait_hours, on_busy, sleep=time.sleep, clock=time.time):
    """Update each pending agent as soon as it's idle, for up to wait_hours; then defer or resume the rest."""
    stacks = render.stacks(cfg)
    pending = pending_agents(cfg)
    updated, deferred, resumed = [], [], {}
    deadline = clock() + wait_hours * 3600
    while pending:
        for a in list(pending):
            if not deploy.agent_busy(a):
                say(f'  {a["id"]} is idle: updating it')
                kind, key = stacks[f'agentlab-agent-{a["id"]}']
                deploy.deploy(cfg, f'agentlab-agent-{a["id"]}', kind, key, plan, force=True)
                updated.append(a['id'])
                pending.remove(a)
        if not pending or clock() >= deadline:
            break
        say(f'  waiting for {", ".join(a["id"] for a in pending)} (a T3 turn is running); next check in 5 min')
        sleep(CHECK_EVERY_S)
    for a in pending:
        if on_busy == 'resume':
            waited = f'still busy after {wait_hours:g} h' if wait_hours else 'busy'
            say(f'  {a["id"]} {waited}: restarting it and resuming its chats')
            kind, key = stacks[f'agentlab-agent-{a["id"]}']
            resumed[a['id']] = resume(cfg, a, kind, key, plan, sleep=sleep)
            updated.append(a['id'])
        else:
            say(f'  {a["id"]} still busy after {wait_hours:g} h: its update waits for the next run')
            deferred.append(a['id'])
    if updated:
        deploy.isolate(cfg, plan)  # Coolify puts recreated containers on its own network too
    return updated, deferred, resumed


# ---------------------------------------------------------------- the command
def update(cfg, config_path, scheduled=False, pulled=None, argv=(), resume_now=False):
    need_root('agentctl update')
    u = cfg['updates']
    try:
        if pulled is None:
            before, after = pull(u['branch'])
            if before != after:
                say(f'  agentlab {before} -> {after}; continuing with the new code')
                os.environ['AGENTLAB_UPDATE_FROM'] = before
                os.execv(sys.executable, [sys.executable, os.path.join(REPO, 'cli', 'agentctl'), *argv, '--pulled'])
            say(f'  agentlab {after} is current')
        frm = os.environ.get('AGENTLAB_UPDATE_FROM') or head()
        plan = Plan(False)
        if images.local(cfg):
            images.build(cfg, plan, force=True)
        else:
            images.pull(cfg, plan)
        applied = apply.apply(cfg, config_path)
        wait_hours, on_busy = (0, 'resume') if resume_now else (u['wait_hours'], u['on_busy'])
        updated, deferred, resumed = wait_for_agents(cfg, plan, wait_hours, on_busy)
    except Failed as e:
        record(cfg, scheduled=scheduled, result='failed', error=str(e), commit=_safe_head())
        raise
    result = 'deferred' if deferred else 'ok'
    return record(
        cfg,
        scheduled=scheduled,
        result=result,
        error='',
        commit_from=frm,
        commit=_safe_head(),
        agents_updated=updated,
        agents_deferred=deferred,
        chats_resumed=resumed,
        companion_templates=applied.get('companion_templates', {}),
    )


def _safe_head():
    try:
        return head()
    except Failed:
        return ''
