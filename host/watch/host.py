import subprocess


def run(cmd: list[str], timeout: float = 120) -> tuple[int, str]:
    """(exit code, combined output) of a command given as an argument list."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, f'{type(e).__name__}: {e}'
    return p.returncode, (p.stdout + p.stderr).strip()


def unit_active(unit: str) -> bool:
    return run(['systemctl', 'is-active', unit])[1] == 'active'


def start_unit(unit: str) -> tuple[int, str]:
    run(['systemctl', 'reset-failed', unit])
    return run(['systemctl', 'start', '--no-block', unit])
