"""Which commands need root; host-changing ones re-run via sudo -n, exit 2 when a password is needed."""

import os
import shlex
import shutil
import subprocess
import sys

from .util import REPO, Needs, is_root

SCRIPT = os.path.join(REPO, 'cli', 'agentctl')


def command(args):
    """('agent', 'add')-style name of the parsed command."""
    return (args.cmd, getattr(args, 'action', None))


def docker_ok():
    if not shutil.which('docker'):
        return False
    try:
        p = subprocess.run(['docker', 'info', '--format', '{{.ID}}'], capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return p.returncode == 0


def readable(path):
    return not path or os.access(path, os.R_OK)


def dry_run_needs_root(args):
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


def _backups_readable(args):
    from . import backup, config  # noqa: PLC0415 - see dry_run_needs_root

    try:
        folder = backup.root(config.load(args.config))
    except PermissionError:
        return False
    return not os.path.exists(folder) or os.access(folder, os.R_OK | os.X_OK)


def needs_root(args):
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


def interactive(args):
    return not args.json and sys.stdin.isatty()


def sudo_argv(args, argv):
    """The same command again as root (--config made absolute, since sudo resets the environment)."""
    flags = [] if interactive(args) else ['-n']
    return ['sudo', *flags, sys.executable, SCRIPT, '--config', os.path.abspath(args.config), *argv]


def elevate(args, argv, execv=None, probe=None):
    """Re-exec through sudo when needed; raise Needs when sudo would prompt and nobody can type."""
    if is_root() or not needs_root(args):
        return
    execv, probe = execv or os.execv, probe or subprocess.run  # looked up per call so tests can patch them
    shown = 'sudo agentctl ' + shlex.join(argv)
    if not shutil.which('sudo'):
        raise _needs(shown, 'sudo is not installed')
    if not interactive(args):
        p = probe(['sudo', '-n', 'true'], capture_output=True, check=False)
        if p.returncode:
            raise _needs(shown, 'it needs root and sudo asks for a password')
    cmd = sudo_argv(args, argv)
    execv(shutil.which('sudo'), cmd)


def _needs(shown, why):
    e = Needs(
        f'{why}: run `{shown}` yourself, or allow passwordless sudo for agentctl '
        f'(e.g. /etc/sudoers.d/agentctl: `<user> ALL=(root) NOPASSWD: {sys.executable} {SCRIPT} *`)'
    )
    e.result = {'needs': 'sudo', 'command': shown}
    return e
