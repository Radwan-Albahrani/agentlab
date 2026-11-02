"""Commands on the host: shell, Docker and systemd units."""

import subprocess


def run(cmd, timeout=120):
    """(exit code, combined output) of a command given as an argument list."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, f'{type(e).__name__}: {e}'
    return p.returncode, (p.stdout + p.stderr).strip()


def unit_active(unit):
    return run(['systemctl', 'is-active', unit])[1] == 'active'


def start_unit(unit):
    run(['systemctl', 'reset-failed', unit])
    return run(['systemctl', 'start', '--no-block', unit])
