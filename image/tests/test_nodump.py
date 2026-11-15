"""The emulator launcher must start the emulator non-dumpable, so a crash never waits on a core dump (#31)."""

import os
import shutil
import signal
import subprocess
import sys

import pytest

IMAGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUMPABLE = 'import ctypes; print(ctypes.CDLL(None).prctl(3, 0, 0, 0, 0))'  # PR_GET_DUMPABLE


@pytest.fixture
def nodump(tmp_path):
    if not shutil.which('gcc'):
        pytest.skip('no C compiler')
    lib = tmp_path / 'nodump.so'
    subprocess.run(['gcc', '-shared', '-fPIC', '-o', lib, os.path.join(IMAGE, 'nodump.c')], check=True)
    return str(lib)


def launch(tmp_path, nodump, body):
    """`android-emulator run` with a stand-in emulator that runs `body` (python) in place of qemu."""
    sdk = tmp_path / 'sdk'
    (sdk / 'emulator').mkdir(parents=True)
    fake = sdk / 'emulator' / 'emulator'
    fake.write_text(f'#!/bin/sh\nexec {sys.executable} -c "{body}"\n')
    fake.chmod(0o755)
    env = {
        **os.environ,
        'ANDROID_SDK_ROOT': str(sdk),
        'ANDROID_AVD_HOME': str(tmp_path / 'avd'),
        'AGENT_NODUMP': nodump,
        'HOME': str(tmp_path),
    }
    return subprocess.run(
        ['bash', os.path.join(IMAGE, 'android-emulator'), 'run'],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_the_emulator_runs_non_dumpable(tmp_path, nodump):
    out = launch(tmp_path, nodump, DUMPABLE)
    assert out.stdout.strip() == '0', out.stderr


def test_a_crashing_emulator_exits_at_once_without_a_core(tmp_path, nodump, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = launch(tmp_path, nodump, 'import os, signal; os.kill(os.getpid(), signal.SIGSEGV)')
    assert out.returncode == -signal.SIGSEGV, out.stderr
    assert not [f for f in os.listdir(tmp_path) if f.startswith('core')]
