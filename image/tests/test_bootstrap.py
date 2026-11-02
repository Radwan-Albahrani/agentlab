"""First-start downloads: they wait until Coolify's temporary network is gone, and none of them can hang for good
(#18: a download begun on that network was stranded when agentlab detached it)."""

import os
import re
import subprocess

from conftest import IMAGE

TOOLS = os.path.join(IMAGE, 'tools.sh')


def run(tmp_path, body, env=None):
    """Run `body` in bash with tools.sh sourced, HOME in tmp_path and sleep a no-op."""
    script = f'source "{TOOLS}"; sleep() {{ :; }}; {body}'
    return subprocess.run(
        ['bash', '-c', script],
        capture_output=True,
        text=True,
        env={**os.environ, 'HOME': str(tmp_path), **(env or {})},
        check=False,
    )


def addresses(tmp_path, *rounds):
    """An `ip` that reports each round's addresses in turn (the last one repeats)."""
    for i, addrs in enumerate(rounds):
        (tmp_path / f'round{i}').write_text(
            ''.join(f'2: eth{n} inet {a}/24 brd x scope global eth{n}\n' for n, a in enumerate(addrs))
        )
    fake = tmp_path / 'bin' / 'ip'
    fake.parent.mkdir(exist_ok=True)
    fake.write_text(
        '#!/bin/bash\n'
        f'n=$(cat {tmp_path}/count 2>/dev/null || echo 0); echo $((n + 1)) > {tmp_path}/count\n'
        f'f={tmp_path}/round$n; [ -f "$f" ] || f={tmp_path}/round{len(rounds) - 1}; cat "$f"\n'
    )
    fake.chmod(0o755)
    return {'PATH': f'{fake.parent}:{os.environ["PATH"]}'}


def test_no_wait_outside_coolify(tmp_path):
    out = run(tmp_path, 'wait_for_final_network; echo done', {'AGENTLAB_WAIT_NETWORK': ''})
    assert out.stdout.strip() == 'done'


def test_starts_at_once_when_already_on_its_own_network(tmp_path):
    env = addresses(tmp_path, ['10.207.1.2']) | {'AGENTLAB_WAIT_NETWORK': '10.207.1.2'}
    out = run(tmp_path, 'wait_for_final_network; echo done', env)
    assert out.stdout.strip() == 'done'
    assert 'waiting' not in out.stdout


def test_waits_until_coolifys_network_is_gone(tmp_path):
    env = addresses(tmp_path, ['10.0.5.3', '10.207.1.2'], ['10.0.5.3', '10.207.1.2'], ['10.207.1.2'])
    out = run(tmp_path, 'wait_for_final_network; echo done', env | {'AGENTLAB_WAIT_NETWORK': '10.207.1.2'})
    assert 'waiting until this container is on its own network only' in out.stdout
    assert 'network settled after 4s' in out.stdout
    assert out.stdout.strip().endswith('done')


def test_gives_up_waiting_after_the_limit(tmp_path):
    env = addresses(tmp_path, ['10.0.5.3', '10.207.1.2']) | {
        'AGENTLAB_WAIT_NETWORK': '10.207.1.2',
        'NETWORK_WAIT_S': '6',
    }
    out = run(tmp_path, 'wait_for_final_network; echo done', env)
    assert 'starting anyway' in out.stdout
    assert out.stdout.strip().endswith('done')


def test_curl_never_waits_on_a_dead_connection(tmp_path):
    run(tmp_path, 'write_curlrc')
    rc = (tmp_path / '.cache' / 'agentlab' / 'curl' / '.curlrc').read_text().split('\n')
    assert {'connect-timeout = 20', 'retry = 5', 'retry-all-errors', 'speed-limit = 1024', 'speed-time = 60'} <= set(rc)


def test_attempt_retries_then_succeeds(tmp_path):
    counter = tmp_path / 'tries'
    cmd = f'n=$(cat {counter} 2>/dev/null || echo 0); echo $((n + 1)) > {counter}; [ "$n" -ge 2 ]'
    out = run(tmp_path, f"attempt demo 5 bash -c '{cmd}' && echo ok")
    assert out.stdout.strip().endswith('ok')
    assert len(re.findall(r'demo: attempt \d failed', out.stdout)) == 2


def test_attempt_cuts_off_a_stall_and_says_so(tmp_path):
    out = run(tmp_path, 'attempt stall 1 bash -c "exec /bin/sleep 30" || echo gave-up')
    assert out.stdout.strip().endswith('gave-up')
    assert out.stdout.count('stalled past its time limit') == 3


def test_every_installer_goes_through_attempt():
    with open(TOOLS) as f:
        text = f.read()
    for name in (
        'Claude Code install',
        'npm install',
        'T3 Code install',
        'herdr install',
        'npm update',
        'claude update',
    ):
        assert f'attempt "{name}"' in text
    # no installer pipes curl into a shell without pipefail (a failed download would look like success)
    for line in text.splitlines():
        if re.search(r'curl .*\| *(ba)?sh', line) and 'NONINTERACTIVE' not in line:
            assert 'set -o pipefail' in line, line


def test_the_entrypoint_waits_for_the_network_before_installing():
    with open(os.path.join(IMAGE, 'entrypoint.sh')) as f:
        text = f.read()
    assert text.index('wait_for_final_network') < text.index('install_missing_tools\n')
