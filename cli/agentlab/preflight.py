"""Host checks the install steps need, run before any change (doctor shows them too)."""

import glob
import os
import platform
import re
import shutil
import subprocess

# The packages host/install/*.sh install from the distro (Docker and cloudflared come from their own repositories).
BASE = ['ca-certificates', 'curl', 'gnupg', 'nftables', 'jq', 'sqlite3', 'e2fsprogs', 'git']
# Java 17+ for Android tools, newest first; keep in step with host/install/65-android-sdk.sh.
JRES = ['openjdk-21-jre-headless', 'openjdk-25-jre-headless', 'openjdk-17-jre-headless']
SYSBOX_ARCH = {'x86_64', 'aarch64'}


def lists_empty():
    return not glob.glob('/var/lib/apt/lists/*Packages')


def candidate(package, run=subprocess.run):
    p = run(['apt-cache', 'policy', package], capture_output=True, text=True, check=False)
    m = re.search(r'Candidate:\s*(\S+)', p.stdout or '')
    return bool(m) and m.group(1) != '(none)'


def jre(run=subprocess.run):
    return next((p for p in JRES if candidate(p, run)), '')


def kernel():
    m = re.match(r'(\d+)\.(\d+)', platform.release())
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def wsl():
    try:
        with open('/proc/version') as f:
            return 'microsoft' in f.read().lower()
    except OSError:
        return False


def problems(cfg, refresh=False, run=subprocess.run):
    """[(id, message, fix)] that would stop an install step; `refresh` updates apt's lists first."""
    out = []
    if not shutil.which('apt-get') or not shutil.which('dpkg'):
        return [
            (
                'host-apt',
                'unsupported host: agentlab installs with apt (Debian or Ubuntu)',
                'use Debian 12/13 or Ubuntu 24.04',
            )
        ]
    if refresh and lists_empty():
        run(['apt-get', 'update', '-qq'], capture_output=True, check=False)
    if lists_empty():
        out.append(('host-packages', "apt's package lists are empty, so packages can't be checked", 'apt-get update'))
    else:
        missing = [p for p in BASE if not candidate(p, run)]
        if missing:
            out.append(
                ('host-packages', f'unsupported host: apt has no {", ".join(missing)}', 'enable the main repository')
            )
    if cfg['isolation'] == 'sysbox':
        if wsl():
            out.append(
                (
                    'host-sysbox',
                    'unsupported host: Sysbox cannot run on WSL',
                    'isolation = "unconfined" (one person only)',
                )
            )
        elif platform.machine() not in SYSBOX_ARCH:
            out.append(
                (
                    'host-sysbox',
                    f'unsupported host: Sysbox has no build for {platform.machine()}',
                    'an x86_64 or arm64 machine',
                )
            )
        elif kernel() < (5, 12):
            out.append(
                (
                    'host-sysbox',
                    f'unsupported host: Sysbox needs Linux 5.12+, this is {platform.release()}',
                    'upgrade the kernel',
                )
            )
    if cfg['android']['enabled']:
        if not os.path.exists('/dev/kvm'):
            out.append(
                (
                    'host-android',
                    'unsupported host: no /dev/kvm for the Android emulator',
                    'bare metal or nested virtualization, or [android] enabled = false',
                )
            )
        if not lists_empty() and not jre(run):
            out.append(
                (
                    'host-android',
                    'unsupported host: apt has no Java 17+ for the Android tools',
                    'enable a repository with openjdk-21/25/17, or [android] enabled = false',
                )
            )
        if not lists_empty() and not candidate('unzip', run):
            out.append(('host-android', 'unsupported host: apt has no unzip', 'enable the main repository'))
    return out
