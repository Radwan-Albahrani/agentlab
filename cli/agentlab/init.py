"""`agentctl init`: PATH, the `agentlab` group and a starter cluster.toml; never overwrites a config."""

import os
import shutil
import sys
from collections.abc import Callable
from typing import Protocol, TypedDict

from . import config
from .util import REPO, Failed, Needs, Plan, run, say

GROUP = 'agentlab'


class Group(Protocol):
    """What init reads of a grp.struct_group."""

    @property
    def gr_gid(self) -> int: ...
    @property
    def gr_mem(self) -> list[str]: ...


GetGroup = Callable[[str], Group | None]


class InitResult(TypedDict):
    next: list[str]


class EditResult(TypedDict, total=False):
    checked: bool
    agents: int


def _group(name: str) -> Group | None:
    import grp  # noqa: PLC0415 - Unix only; agentctl's other commands still import on any OS

    try:
        return grp.getgrnam(name)
    except KeyError:
        return None


def link(plan: Plan, bin_dir: str, target: str) -> None:
    path = os.path.join(bin_dir, 'agentctl')
    if os.path.realpath(path) == os.path.realpath(target) and os.path.islink(path):
        return
    if os.path.exists(path) and not os.path.islink(path):
        raise Failed(f'{path} exists and is not a link to agentlab: move it away, then re-run agentctl init')

    def make() -> None:
        os.makedirs(bin_dir, exist_ok=True)
        if os.path.islink(path):
            os.remove(path)
        os.symlink(target, path)

    plan.do(f'link {path} -> {target}', fn=make)


def group(plan: Plan, name: str, user: str, get: GetGroup = _group) -> bool:
    if get(name) is None:
        plan.do(f'create group {name}', ['groupadd', '--system', name])
    if user and user != 'root':
        g = get(name)
        if not (g and user in g.gr_mem):
            plan.do(f'add {user} to group {name}', ['usermod', '-aG', name, user])
            return True
    return False


def config_file(plan: Plan, path: str, example: str, name: str, get: GetGroup = _group) -> None:
    if os.path.exists(path):
        say(f'  kept {path} (init never overwrites it)')
        # a pre-existing config must stay readable by the group; only ownership and mode change, never content
        g = get(name)
        st = os.stat(path)
        if g and (st.st_gid != g.gr_gid or st.st_mode & 0o777 != 0o640):
            gid = g.gr_gid

            def own() -> None:
                os.chown(path, 0, gid)
                os.chmod(path, 0o640)

            plan.do(f'set {path} to root:{name} 0640', fn=own)
        return

    def make() -> None:
        os.makedirs(os.path.dirname(path), mode=0o755, exist_ok=True)
        shutil.copyfile(example, path + '.tmp')
        os.chmod(path + '.tmp', 0o640)
        g = get(name)
        os.chown(path + '.tmp', 0, g.gr_gid if g else 0)
        os.replace(path + '.tmp', path)

    plan.do(f'create {path} from cluster.example.toml (root:{name} 0640)', fn=make)


def init(
    config_path: str,
    bin_dir: str = '/usr/local/bin',
    user: str | None = None,
    get: GetGroup = _group,
    plan: Plan | None = None,
) -> InitResult:
    plan = plan or Plan(False)
    user = user if user is not None else os.environ.get('SUDO_USER', '')
    link(plan, bin_dir, os.path.join(REPO, 'cli', 'agentctl'))
    joined = group(plan, GROUP, user, get)
    config_file(plan, config_path, os.path.join(REPO, 'cluster.example.toml'), GROUP, get)
    steps = [
        'agentctl setup             # a few questions, then everything is installed and started',
        f'(or edit {config_path} yourself, then: agentctl install && agentctl apply)',
    ]
    if joined:
        steps.insert(0, f'log out and back in (or run `newgrp {GROUP}`) so {user} is in the {GROUP} group')
    say('next:')
    for s in steps:
        say(f'  {s}')
    return {'next': steps}


def edit(
    config_path: str,
    editor: str | None = None,
    runner: Callable[..., tuple[int, str]] = run,
    isatty: bool | None = None,
) -> EditResult:
    """Edit the config in $VISUAL / $EDITOR (via sudoedit when not writable), then check it."""
    if not (isatty if isatty is not None else sys.stdin.isatty()):
        raise Needs(f'config edit opens an editor and needs a terminal: edit {config_path} directly instead')
    if not os.path.exists(config_path):
        raise Failed(f'{config_path} not found: run agentctl init first')
    editor = editor or os.environ.get('VISUAL') or os.environ.get('EDITOR') or 'nano'
    if os.access(config_path, os.W_OK):
        runner(['sh', '-c', f'{editor} "$1"', 'editor', config_path], check=False, capture=False)
    else:
        runner(['sudoedit', config_path], check=False, capture=False, env={**os.environ, 'SUDO_EDITOR': editor})
    try:
        cfg = config.load(config_path)
    except PermissionError:
        say(f'saved; you cannot read {config_path} to check it: run agentctl doctor (as a member of {GROUP})')
        return {'checked': False}
    say(f'{config_path} is valid: {len(cfg["agents"])} agents, auth {cfg["auth"]["mode"]}')
    return {'checked': True, 'agents': len(cfg['agents'])}
