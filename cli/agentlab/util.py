"""Small helpers every command shares: output for people or (--json) for agents, running commands (or only
printing them on a dry run), sizes, atomic writes. agentctl is driven by AI agents over SSH as much as by people, so
nothing prompts: exit 0 = done, 1 = failed, 2 = needs --yes or a manual step (the output says which)."""

import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AGENT_UID = 1000  # the agent user inside the image; host files it uses are owned by this uid (see disks.py)
OK, FAILED, NEEDS = 0, 1, 2


class Failed(Exception):  # noqa: N818 - agentctl's one error type; Needs is a kind of it
    """A command or check failed in a way the user must fix; printed without a traceback."""

    code = FAILED


class Needs(Failed):
    """Stopped before doing anything: re-run with --yes, or do the manual step in the message first."""

    code = NEEDS


class Output:
    """With --json, messages, warnings and changes are collected and printed once as JSON at the end."""

    def __init__(self):
        self.json = False
        self.messages, self.warnings, self.changes = [], [], []


OUT = Output()


def say(*parts):
    text = ' '.join(str(p) for p in parts)
    if OUT.json:
        OUT.messages.append(text.strip())
    else:
        print(text, flush=True)


def warn(msg):
    if OUT.json:
        OUT.warnings.append(msg)
    else:
        print(f'! {msg}', file=sys.stderr, flush=True)


def run(cmd, *, check=True, capture=True, timeout=600, input_text=None, env=None):
    """(exit code, output) of an argument list; raises Failed on a non-zero exit when check is set. A program that
    isn't installed is exit 127, like a shell's, so checks report it instead of crashing."""
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

    def __init__(self, dry):
        self.dry = dry

    def do(self, what, cmd=None, fn=None):
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


def size_bytes(text):
    m = SIZE.match(str(text).strip())
    if not m:
        raise ValueError(f'not a size: {text!r} (use e.g. 12g or 60G)')
    return int(float(m.group(1)) * UNITS[m.group(2).lower()])


def gb(text):
    return round(size_bytes(text) / 2**30, 1)


def write_if_changed(path, text, mode=None):
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


def differs(path, text):
    try:
        with open(path) as f:
            return f.read() != text
    except OSError:
        return True


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def agent_folder(home, rel, create=True):
    """host/safe.py's Folder: a folder inside an agent's home, opened without following the agent's symlinks."""
    host = os.path.join(REPO, 'host')
    if host not in sys.path:
        sys.path.insert(0, host)
    import safe  # noqa: PLC0415 - lives with the host services, which use it the same way

    return safe.Folder(home, rel, create=create)


def is_root():
    return hasattr(os, 'geteuid') and os.geteuid() == 0


def need_root(what):
    if not is_root():
        raise Failed(f'{what} needs root: run it with sudo')
