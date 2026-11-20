"""`agentctl update`: fast-forward pull, images, apply, then wait for busy agents ([updates] on_busy)."""

import datetime
import json
import os
import sys
import time
from collections.abc import Callable, Sequence
from typing import Literal, NamedTuple, TypedDict, Unpack

from . import apply, deploy, images, render, template
from .config import AgentCfg, Cluster
from .coolify import StackKind
from .fsm import Machine
from .util import REPO, Failed, Plan, load_json, need_root, run, say

CHECK_EVERY_S = 300

Outcome = Literal['ok', 'deferred', 'failed']  # failed: an exception; deferred: an agent still waits for its update
OnBusy = Literal['defer', 'resume']
AgentStep = Literal['pending', 'updated', 'resumed', 'deferred']

# An agent's step while an update waits for it (wait_for_agents):
#   pending   apply left it out because a T3 turn was running     updated   it went idle, so it was deployed
#   resumed   still busy at the deadline, restarted anyway (on_busy = 'resume'; T3 resumes its cut-off turns)
#   deferred  still busy at the deadline: its update waits for the next run
STEP: Machine[AgentStep] = Machine(
    'agent update', {'pending': ('updated', 'resumed', 'deferred'), 'updated': (), 'resumed': (), 'deferred': ()}
)


class Record(TypedDict, total=False):
    """state/update.json: the last update's outcome (a failed one carries only at, scheduled, result, error, commit)."""

    at: str
    scheduled: bool
    result: Outcome
    error: str
    commit_from: str
    commit: str
    agents_updated: list[str]
    agents_deferred: list[str]
    chats_resumed: dict[str, list[str]]
    companion_templates: dict[str, template.Result]


class Waited(NamedTuple):
    """Where each pending agent ended up: updated (idle, or restarted anyway), deferred, and the chats cut off."""

    updated: list[str]
    deferred: list[str]
    resumed: dict[str, list[str]]


def state_path(cfg: Cluster) -> str:
    return os.path.join(cfg['data'], 'state', 'update.json')


def last(cfg: Cluster) -> Record:
    return load_json(state_path(cfg), Record()) or Record()


def record(cfg: Cluster, **result: Unpack[Record]) -> Record:
    path = state_path(cfg)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    result['at'] = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    with open(path + '.tmp', 'w') as f:
        json.dump(result, f, indent=2)
    os.replace(path + '.tmp', path)
    return result


def git(*args: str, check: bool = True) -> tuple[int, str]:
    return run(['git', '-C', REPO, *args], check=check)


def head() -> str:
    return git('rev-parse', '--short', 'HEAD')[1].strip()


def pull(branch: str) -> tuple[str, str]:
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


def inflight(cfg: Cluster, agent: AgentCfg) -> list[tuple[str, str]]:
    """[(run id, thread id)] of T3 turns without a finished status, as the agent reports them; none when it is
    stopped or can't answer."""
    got = deploy.ask_t3(cfg, agent, 'inflight')
    if not isinstance(got, list):
        return []
    out = []
    for row in got:
        match row:
            case [str(run_id), str(thread_id)]:
                out.append((run_id, thread_id))
            case _:
                return []  # garbage
    return out


def resume(cfg: Cluster, agent: AgentCfg, kind: StackKind, key: str | None, plan: Plan) -> list[str]:
    """Restart a busy agent anyway (T3 resumes the cut-off turns itself). -> the chats that were mid-turn"""
    running = sorted({thread for _, thread in inflight(cfg, agent)})
    deploy.deploy(cfg, f'agentlab-agent-{agent["id"]}', kind, key, plan, force=True)
    return running


def pending_agents(cfg: Cluster) -> list[AgentCfg]:
    """Agents apply left out because a T3 turn was running: a newer image, or a changed file, not live yet."""
    out: list[AgentCfg] = []
    for a in cfg['agents']:
        stack = f'agentlab-agent-{a["id"]}'
        path = deploy.compose_file(cfg, stack)
        if not os.path.isfile(path) or deploy.deployed_this_run(stack):
            continue
        with open(path) as f:
            text = f.read()
        if deploy.changed_since_deploy(cfg, stack, text) or deploy.stale_images(cfg, stack):
            out.append(a)
    return out


def wait_for_agents(
    cfg: Cluster,
    plan: Plan,
    wait_hours: float,
    on_busy: OnBusy,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.time,
) -> Waited:
    """Update each pending agent as soon as it's idle, for up to wait_hours; then defer or resume the rest."""
    stacks = render.stacks(cfg)
    agents = pending_agents(cfg)
    step: dict[str, AgentStep] = {a['id']: STEP.first('pending') for a in agents}
    went: list[str] = []  # updated or resumed, in the order they went
    resumed: dict[str, list[str]] = {}
    deadline = clock() + wait_hours * 3600

    def pending() -> list[AgentCfg]:
        return [a for a in agents if step[a['id']] == 'pending']

    while pending():
        for a in pending():
            if not deploy.agent_busy(cfg, a):
                say(f'  {a["id"]} is idle: updating it')
                kind, key = stacks[f'agentlab-agent-{a["id"]}']
                deploy.deploy(cfg, f'agentlab-agent-{a["id"]}', kind, key, plan, force=True)
                step[a['id']] = STEP.to(step[a['id']], 'updated')
                went.append(a['id'])
        if not pending() or clock() >= deadline:
            break
        say(f'  waiting for {", ".join(a["id"] for a in pending())} (a T3 turn is running); next check in 5 min')
        sleep(CHECK_EVERY_S)
    for a in pending():
        if on_busy == 'resume':
            waited = f'still busy after {wait_hours:g} h' if wait_hours else 'busy'
            say(f'  {a["id"]} {waited}: restarting it (T3 resumes its turns)')
            kind, key = stacks[f'agentlab-agent-{a["id"]}']
            resumed[a['id']] = resume(cfg, a, kind, key, plan)
            step[a['id']] = STEP.to(step[a['id']], 'resumed')
            went.append(a['id'])
        else:
            say(f'  {a["id"]} still busy after {wait_hours:g} h: its update waits for the next run')
            step[a['id']] = STEP.to(step[a['id']], 'deferred')
    if went:
        deploy.isolate(cfg, plan)
    return Waited(went, [aid for aid, s in step.items() if s == 'deferred'], resumed)


def update(
    cfg: Cluster,
    config_path: str,
    scheduled: bool = False,
    pulled: bool | None = None,
    argv: Sequence[str] = (),
    resume_now: bool = False,
) -> Record:
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
        wait_hours: float
        on_busy: OnBusy
        wait_hours, on_busy = (0, 'resume') if resume_now else (u['wait_hours'], u['on_busy'])
        updated, deferred, resumed = wait_for_agents(cfg, plan, wait_hours, on_busy)
    except Failed as e:
        record(cfg, scheduled=scheduled, result='failed', error=str(e), commit=_safe_head())
        raise
    result: Outcome = 'deferred' if deferred else 'ok'
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


def _safe_head() -> str:
    try:
        return head()
    except Failed:
        return ''
