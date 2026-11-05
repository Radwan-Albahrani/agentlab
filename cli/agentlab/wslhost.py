"""On WSL: the Windows task that starts this distro at boot and again whenever it stops ([cluster] wsl_autostart)."""

import base64
import os
import re

from .util import REPO, run, warn, write_if_changed

POWERSHELL = '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'
TASK = r"-TaskPath '\agentlab\' -TaskName 'Autostart'"
SCRIPT = os.path.join(REPO, 'host', 'wsl', 'autostart.ps1')
TRIGGERS = {'MSFT_TaskBootTrigger': 'boot', 'MSFT_TaskLogonTrigger': 'sign-in'}


def is_wsl():
    try:
        with open('/proc/version') as f:
            return 'microsoft' in f.read().lower()
    except OSError:
        return False


def distro(cfg, save=True):
    """This distro's name: WSL sets it for commands started from Windows; systemd services remember the last one."""
    saved = os.path.join(cfg['data'], 'state', 'wsl-distro')
    name = os.environ.get('WSL_DISTRO_NAME', '')
    if re.fullmatch(r'[\w.-]+', name):
        if save:
            write_if_changed(saved, name + '\n')
        return name
    try:
        with open(saved) as f:
            return f.read().strip()
    except OSError:
        return ''


def ps(command):
    """(exit code, output) of a Windows PowerShell command."""
    return run([POWERSHELL, '-NoProfile', '-NonInteractive', '-Command', command], check=False, timeout=120)


def arguments(name):
    """The task's powershell.exe arguments: the loop itself, encoded, so no file on the Windows side can go stale."""
    with open(SCRIPT) as f:
        body = ''.join(line for line in f if not line.lstrip().startswith('#'))
    code = base64.b64encode(f"$Distro = '{name}'\n{body}".encode('utf-16-le')).decode()
    return f'-NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand {code}'


def task():
    """(state, 'boot' or 'sign-in', arguments) of the registered task, or None."""
    rc, out = ps(
        f'$t = Get-ScheduledTask {TASK} -ErrorAction SilentlyContinue; '
        'if ($t) { [string]$t.State; $t.Triggers[0].CimClass.CimClassName; $t.Actions[0].Arguments }'
    )
    lines = [x.strip() for x in out.splitlines() if x.strip()]
    return (lines[0], TRIGGERS.get(lines[1], lines[1]), lines[2]) if rc == 0 and len(lines) >= 3 else None


def register(want):
    """In one PowerShell call: leave a matching task alone, else (re)register it, at boot when Windows lets us
    (admin) or else at sign-in, and start it. -> 'same', 'boot', 'sign-in', or '' on failure"""
    rc, out = ps(
        f"$want = '{want}'; "
        f'$t = Get-ScheduledTask {TASK} -ErrorAction SilentlyContinue; '
        "if ($t -and $t.Actions[0].Arguments -eq $want) { 'same'; return }; "
        "$a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $want; "
        '$s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit 0 -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries '
        '-MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1); '
        '$me = "$env:USERDOMAIN\\$env:USERNAME"; '
        'try { '
        '$p = New-ScheduledTaskPrincipal -UserId $me -LogonType S4U -RunLevel Highest; '
        f'Register-ScheduledTask {TASK} -Action $a -Trigger (New-ScheduledTaskTrigger -AtStartup) -Principal $p '
        "-Settings $s -Force -ErrorAction Stop | Out-Null; $how = 'boot' "
        '} catch { '
        '$p = New-ScheduledTaskPrincipal -UserId $me -LogonType Interactive; '
        f'Register-ScheduledTask {TASK} -Action $a -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $me) '
        "-Principal $p -Settings $s -Force | Out-Null; $how = 'sign-in' "
        '}; '
        # a running copy of the old loop keeps the distro up; the new one takes over from the next boot
        f"if ((Get-ScheduledTask {TASK}).State -ne 'Running') {{ Start-ScheduledTask {TASK} }}; $how"
    )
    found = re.findall(r'^(same|boot|sign-in)\s*$', out, re.M)
    if rc or not found:
        warn(f'could not register the WSL autostart task: {out.strip()[:300]}')
        return ''
    return found[-1]


def ensure(cfg, plan):
    """Register (or, with wsl_autostart = false, remove) the task; problems only warn, they never stop an apply."""
    if not is_wsl() or not os.access(POWERSHELL, os.X_OK):
        return
    if not cfg['wsl_autostart']:
        _, out = ps(f'if (Get-ScheduledTask {TASK} -ErrorAction SilentlyContinue) {{ "found" }}')
        if 'found' in out:
            plan.do(
                'remove the WSL autostart task ([cluster] wsl_autostart = false)',
                fn=lambda: ps(f'Unregister-ScheduledTask {TASK} -Confirm:$false'),
            )
        return
    name = distro(cfg, save=not plan.dry)
    if not name:
        warn('WSL autostart: run agentctl apply once from a WSL terminal so it learns the distro name')
        return
    if plan.dry:
        t = task()
        if not t or t[2] != arguments(name):
            plan.do(f'register the WSL autostart task for {name}')
        return
    how = register(arguments(name))
    if how in ('boot', 'sign-in'):
        plan.do(f'registered the WSL autostart task for {name} (starts at {how})')
    if how == 'sign-in':
        warn(
            'WSL autostart starts at Windows sign-in: run `agentctl apply` once from a WSL terminal opened as '
            'administrator so it starts at boot, signed in or not'
        )
