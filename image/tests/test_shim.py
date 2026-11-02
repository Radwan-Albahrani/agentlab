"""The throttle shim's classification must stay exactly as recorded in shim_expected.txt ("heavy|light <command>")."""

import os
import subprocess

import pytest

SHIM = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'throttle', 'shim')
CASES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shim_expected.txt')


def cases():
    with open(CASES) as f:
        for line in f:
            verdict, _, command = line.strip().partition(' ')
            if command:
                yield command, verdict


def classify(command):
    tool, *args = command.split()
    script = f'. {SHIM}; tool=$1; shift; is_heavy "$@" && echo heavy || echo light'
    return subprocess.run(
        ['bash', '-c', script, '_', tool, *args], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.mark.parametrize(('command', 'verdict'), list(cases()))
def test_classification(command, verdict):
    assert classify(command) == verdict


def test_tools_table_is_what_shim_sync_reads():
    with open(SHIM) as f:
        tools_line = next(line for line in f if line.startswith('TOOLS="'))
    assert {'npm', 'bun', 'turbo', 'nx', 'cargo', 'docker'} <= set(tools_line.split('"')[1].split())
