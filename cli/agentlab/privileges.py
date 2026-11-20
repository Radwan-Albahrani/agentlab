"""Which commands need root; host-changing ones re-run via sudo -n, exit 2 when a password is needed."""

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable

from .util import REPO, Needs, is_root

SCRIPT = os.path.join(REPO, 'cli', 'agentctl')
Execv = Callable[[str, list[str]], object]  # os.execv, or a test's stand-in
Probe = Callable[..., subprocess.CompletedProcess[bytes]]  # subprocess.run, or a test's stand-in


def command(args: argparse.Namespace) -> tuple[str, str | None]:
    """('agent', 'add')-style name of the parsed command."""
    return (args.cmd, getattr(args, 'action', None))


def docker_ok() -> bool:
    if not shutil.which('docker'):
        return False
    try:
        p = subprocess.run(['docker', 'info', '--format', '{{.ID}}'], capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return p.returncode == 0


def readable(path: str) -> bool:
    return not path or os.access(path, os.R_OK)


def dry_run_needs_root(args: argparse.Namespace) -> bool:
    """Whether a dry run needs root: only when the caller can't read the config, Docker or the Cloudflare token."""
    from . import config  # noqa: PLC0415 - config imports util only; kept lazy so --help stays instant

    if not readable(args.config):
        return True
    try:
        cfg = config.load(args.config)
    except PermissionError:
        return True
    if not docker_ok():
        return True
    token = cfg['cloudflare'].get('api_token_file')
    folder = os.path.dirname(token)
    if os.path.isdir(folder) and not os.access(folder, os.R_OK | os.X_OK):
        return True
    return os.path.exists(token) and not readable(token)


def _backups_readable(args: argparse.Namespace) -> bool:
    from . import backup, config  # noqa: PLC0415 - see dry_run_needs_root

    try:
        folder = backup.root(config.load(args.config))
    except PermissionError:
        return False
    return not os.path.exists(folder) or os.access(folder, os.R_OK | os.X_OK)


def needs_root(args: argparse.Namespace) -> bool:
    """True when this command must run as root."""
    cmd, action = command(args)
    if cmd in ('doctor', 'status', 'config') or (cmd, action) == ('agent', 'list'):
        return False
    if (cmd, action) == ('backup', 'list'):
        return not _backups_readable(args)
    if cmd == 'images':
        return not docker_ok()
    if getattr(args, 'dry_run', False):
        return dry_run_needs_root(args) if cmd == 'apply' else not readable(args.config)
    if (cmd, action) == ('agent', 'remove') and not (args.yes or args.keep_data):
        return not readable(args.config)
    return True


def interactive(args: argparse.Namespace) -> bool:
    return not args.json and sys.stdin.isatty()


def sudo_argv(args: argparse.Namespace, argv: list[str]) -> list[str]:
    """The same command again as root (--config made absolute, since sudo resets the environment)."""
    flags = [] if interactive(args) else ['-n']
    return ['sudo', *flags, sys.executable, SCRIPT, '--config', os.path.abspath(args.config), *argv]


def elevate(args: argparse.Namespace, argv: list[str], execv: Execv | None = None, probe: Probe | None = None) -> None:
    """Re-exec through sudo when needed; raise Needs when sudo would prompt and nobody can type."""
    if is_root() or not needs_root(args):
        return
    execv, probe = execv or os.execv, probe or subprocess.run  # looked up per call so tests can patch them
    shown = 'sudo agentctl ' + shlex.join(argv)
    sudo = shutil.which('sudo')
    if not sudo:
        raise _needs(shown, 'sudo is not installed')
    if not interactive(args):
        p = probe(['sudo', '-n', 'true'], capture_output=True, check=False)
        if p.returncode:
            raise _needs(shown, 'it needs root and sudo asks for a password')
    cmd = sudo_argv(args, argv)
    execv(sudo, cmd)


def _needs(shown: str, why: str) -> Needs:
    e = Needs(
        f'{why}: run `{shown}` yourself, or allow passwordless sudo for agentctl '
        f'(e.g. /etc/sudoers.d/agentctl: `<user> ALL=(root) NOPASSWD: {sys.executable} {SCRIPT} *`)'
    )
    e.result = {'needs': 'sudo', 'command': shown}
    return e
