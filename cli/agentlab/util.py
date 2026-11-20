"""Shared helpers: output (--json for agents), running commands, dry runs, atomic writes; nothing prompts."""

import importlib
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, Self, TypedDict

Json = dict[str, Any]  # a parsed JSON object of no fixed shape

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AGENT_UID = 1000  # the agent user inside the image; host files it uses are owned by this uid (see disks.py)
OK, FAILED, NEEDS = 0, 1, 2


class Failed(Exception):  # noqa: N818 - agentctl's one error type; Needs is a kind of it
    """A command or check failed in a way the user must fix; printed without a traceback."""

    code = FAILED
    result: Json  # set by some raisers: the --json result to report with the error


class Needs(Failed):
    """Stopped before doing anything: re-run with --yes, or do the manual step in the message first."""

    code = NEEDS


class Change(TypedDict):
    change: str
    command: list[str] | None
    done: bool


class Output:
    """With --json, messages, warnings and changes are collected and printed once as JSON at the end."""

    def __init__(self) -> None:
        self.json = False
        self.messages: list[str] = []
        self.warnings: list[str] = []
        self.changes: list[Change] = []


OUT = Output()


def say(*parts: object) -> None:
    text = ' '.join(str(p) for p in parts)
    if OUT.json:
        OUT.messages.append(text.strip())
    else:
        print(text, flush=True)


def warn(msg: str) -> None:
    if OUT.json:
        OUT.warnings.append(msg)
    else:
        print(f'! {msg}', file=sys.stderr, flush=True)


def run(
    cmd: Sequence[str],
    *,
    check: bool = True,
    capture: bool = True,
    timeout: float = 600,
    input_text: str | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[int, str]:
    """(exit code, output); raises Failed on non-zero when check is set; a missing program is exit 127."""
    try:
        p = subprocess.run(
            cmd, capture_output=capture, text=True, timeout=timeout, check=False, input=input_text, env=env
        )
    except FileNotFoundError:
        if check:
            raise Failed(f'{cmd[0]} is not installed (needed for: {" ".join(cmd)})') from None
        return 127, f'{cmd[0]}: not installed'
    out = ((p.stdout or '') + (p.stderr or '')).strip() if capture else ''
    if check and p.returncode:
        raise Failed(f'{" ".join(cmd)} failed ({p.returncode}): {out[-600:]}')
    return p.returncode, out


class Plan:
    """Runs changes for real, or on a dry run only prints them. Reads always run: a dry run must see the real state."""

    def __init__(self, dry: bool) -> None:
        self.dry = dry

    def do(self, what: str, cmd: list[str] | None = None, fn: Callable[[], object] | None = None) -> object:
        OUT.changes.append({'change': what, 'command': cmd, 'done': not self.dry})
        if self.dry:
            say(f'  would {what}' + (f': {" ".join(cmd)}' if cmd else ''))
            return None
        say(f'  {what}')
        if cmd:
            return run(cmd)[1]
        return fn() if fn else None


SIZE = re.compile(r'^(\d+(?:\.\d+)?)([kmgt]?)b?$', re.IGNORECASE)
UNITS = {'': 1, 'k': 2**10, 'm': 2**20, 'g': 2**30, 't': 2**40}


def size_bytes(text: object) -> int:
    m = SIZE.match(str(text).strip())
    if not m:
        raise ValueError(f'not a size: {text!r} (use e.g. 12g or 60G)')
    return int(float(m.group(1)) * UNITS[m.group(2).lower()])


def gb(text: object) -> float:
    return round(size_bytes(text) / 2**30, 1)


def write_if_changed(path: str, text: str, mode: int | None = None) -> bool:
    """True when the file was (re)written. Atomic, so readers never see half a file."""
    try:
        with open(path) as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + '.tmp', 'w', newline='\n') as f:
        f.write(text)
    if mode is not None:
        os.chmod(path + '.tmp', mode)
    os.replace(path + '.tmp', path)
    return True


def differs(path: str, text: str) -> bool:
    try:
        with open(path) as f:
            return f.read() != text
    except OSError:
        return True


def load_json(path: str, default: Any = None) -> Any:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


class Folder(Protocol):
    """What agentctl uses of host/safe.py's Folder (that module lives outside this package)."""

    def __enter__(self) -> Self: ...
    def __exit__(self, *exc: object) -> None: ...
    def names(self, suffix: str = '') -> list[str]: ...
    def is_file(self, name: str) -> bool: ...
    def mtime(self, name: str) -> float: ...
    def read(self, name: str, limit: int = 65536) -> str | None: ...
    def read_json(self, name: str) -> Any: ...
    def write(self, name: str, text: str, uid: int = ..., mode: int = ...) -> None: ...
    def write_json(self, name: str, data: object, uid: int = ..., mode: int = ...) -> None: ...
    def exists(self, name: str) -> bool: ...
    def remove(self, name: str) -> None: ...


def agent_folder(home: str, rel: str, create: bool = True) -> Folder:
    """host/safe.py's Folder: a folder inside an agent's home, opened without following the agent's symlinks."""
    host = os.path.join(REPO, 'host')
    if host not in sys.path:
        sys.path.insert(0, host)
    safe = importlib.import_module('safe')  # lives with the host services, which use it the same way
    folder: Folder = safe.Folder(home, rel, create=create)
    return folder


def is_root() -> bool:
    return hasattr(os, 'geteuid') and os.geteuid() == 0


def need_root(what: str) -> None:
    if not is_root():
        raise Failed(f'{what} needs root: run it with sudo')


LOCK = '/run/agentlab-agentctl.lock'  # held by the agentctl change running now


def lock_holder(path: str = LOCK) -> str:
    """'pid N (agentctl …), for 3h' from what the holder wrote into the lock file, or ''."""
    try:
        with open(path) as f:
            text = f.read().strip()
        age = time.time() - os.path.getmtime(path)
    except OSError:
        return ''
    if not text:
        return ''
    pid, _, cmd = text.partition(' ')
    return f'pid {pid} (agentctl {cmd}), for {age / 3600:.1f} h'
