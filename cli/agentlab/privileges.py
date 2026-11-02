"""Which commands need root, and getting it. Commands that change the host re-run themselves through sudo, so nobody
types `sudo agentctl`; read-only ones never elevate. AI agents drive agentctl without a terminal: there sudo must not
sit on a password prompt, so it runs with -n and, when that is refused, agentctl stops with exit 2 and
{needs: "sudo"} for the human to run or to allow."""

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
    """A dry run only reads, so it runs as the caller when the caller can read everything it reads: the config,
    Docker, and the Cloudflare token when Cloudflare is set up."""
    from . import config  # noqa: PLC0415 - config imports util only; kept lazy so --help stays instant

    if not readable(args.config):
        return True
    try:
        cfg = config.load(args.config)
    except PermissionError:
        return True
    if not docker_ok():
        return True
    return not readable(cfg['cloudflare'].get('api_token_file'))


def _backups_readable(args):
    from . import backup, config  # noqa: PLC0415 - see dry_run_needs_root

    try:
        folder = backup.root(config.load(args.config))
    except PermissionError:
        return False
    return not os.path.exists(folder) or os.access(folder, os.R_OK | os.X_OK)


def needs_root(args):
    """True when this command must run as root. Read-only commands never do."""
    cmd, action = command(args)
    if cmd in ('doctor', 'status', 'config') or (cmd, action) == ('agent', 'list'):
        return False
    if (cmd, action) == ('backup', 'list'):
        return not _backups_readable(args)  # they hold everyone's chats, so the folder is root-only
    if cmd == 'images':
        return not docker_ok()
    if getattr(args, 'dry_run', False):
        return dry_run_needs_root(args) if cmd == 'apply' else not readable(args.config)
    if (cmd, action) == ('agent', 'remove') and not (args.yes or args.keep_data):
        return not readable(args.config)  # only prints the plan and stops for --yes
    return True


def interactive(args):
    return not args.json and sys.stdin.isatty()


def sudo_argv(args, argv):
    """The same command again as root. sudo resets the environment, so --config travels as an absolute path."""
    flags = [] if interactive(args) else ['-n']
    return ['sudo', *flags, sys.executable, SCRIPT, '--config', os.path.abspath(args.config), *argv]


def elevate(args, argv, execv=os.execv, probe=subprocess.run):
    """Return when already root or not needed; otherwise replace this process with the sudo'd one, or raise Needs
    when sudo can't run without a password and nobody is there to type it."""
    if is_root() or not needs_root(args):
        return
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
