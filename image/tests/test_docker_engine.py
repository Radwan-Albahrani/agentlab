"""Which Docker engine an agent gets: root dockerd through one sudo rule under Sysbox, rootless otherwise."""

import os
import re
import subprocess

import pytest
from conftest import IMAGE


def stub(tmp_path, name):
    path = tmp_path / name
    path.write_text(f'#!/bin/sh\necho "{name} $*"\n')
    path.chmod(0o755)


def engine(tmp_path, isolation):
    for name in ('sudo', 'dockerd-rootless.sh'):
        stub(tmp_path, name)
    env = {**os.environ, 'PATH': f'{tmp_path}:{os.environ["PATH"]}', 'AGENTLAB_ISOLATION': isolation}
    out = subprocess.run(
        ['bash', os.path.join(IMAGE, 'agent-dockerd')], capture_output=True, text=True, env=env, check=True
    )
    return out.stdout.strip()


def test_sysbox_runs_the_root_engine_through_sudo(tmp_path):
    assert engine(tmp_path, 'sysbox') == 'sudo -n /usr/local/sbin/agent-dockerd-root'


@pytest.mark.parametrize('isolation', ['unconfined', ''])
def test_otherwise_rootless(tmp_path, isolation):
    assert engine(tmp_path, isolation) == 'dockerd-rootless.sh -H unix:///run/user/1000/dockerd.sock'


def test_root_engine_refuses_outside_a_user_namespace():
    with open('/proc/self/uid_map') as f:
        if f.read().split() != ['0', '0', '4294967295']:
            pytest.skip('this test host runs in a user namespace')
    out = subprocess.run(
        ['bash', os.path.join(IMAGE, 'agent-dockerd-root')], capture_output=True, text=True, check=False
    )
    assert out.returncode == 1
    assert 'not in a user namespace' in out.stderr


def test_the_root_engine_socket_is_for_group_docker_only():
    with open(os.path.join(IMAGE, 'agent-dockerd-root')) as f:
        text = f.read()
    assert 'exec /usr/bin/dockerd -H unix:///run/user/1000/dockerd.sock --group docker' in text


def test_sudo_allows_exactly_one_command():
    with open(os.path.join(IMAGE, 'Dockerfile')) as f:
        dockerfile = f.read()
    rules = re.findall(r"echo '(agent [^']*)' > /etc/sudoers\.d/", dockerfile)
    assert rules == ['agent ALL=(root) NOPASSWD: /usr/local/sbin/agent-dockerd-root ""']  # "": no arguments
    assert 'usermod -aG docker agent' in dockerfile
    assert 'COPY --chmod=755 agent-dockerd-root /usr/local/sbin/' in dockerfile


def test_supervisord_starts_the_engine_through_the_wrapper():
    with open(os.path.join(IMAGE, 'supervisord.conf')) as f:
        conf = f.read()
    section = conf.split('[program:dockerd]', 1)[1].split('[program:', 1)[0]
    assert 'command=nice -n 10 /usr/local/bin/agent-dockerd' in section
    assert 'autostart=false' in section


def test_scripts_are_bash():
    for name in ('agent-dockerd', 'agent-dockerd-root'):
        with open(os.path.join(IMAGE, name)) as f:
            assert f.readline() == '#!/bin/bash\n'
