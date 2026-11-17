import os
import re
import subprocess

from conftest import IMAGE

TOOLS = os.path.join(IMAGE, 'tools.sh')


def run(tmp_path, body, env=None):
    script = f'source "{TOOLS}"; sleep() {{ :; }}; {body}'
    return subprocess.run(
        ['bash', '-c', script],
        capture_output=True,
        text=True,
        env={**os.environ, 'HOME': str(tmp_path), **(env or {})},
        check=False,
    )


def addresses(tmp_path, *rounds):
    """A fake `ip` reporting each round's addresses in turn (the last one repeats)."""
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
        'Bun install',
        'bun ${1}',
        'bun upgrade',
        'T3 Code install',
        'herdr install',
        'claude update',
    ):
        assert f'attempt "{name}"' in text
    for line in text.splitlines():
        if re.search(r'curl .*\| *(ba)?sh', line) and 'NONINTERACTIVE' not in line:
            assert 'set -o pipefail' in line, line


def test_the_entrypoint_waits_for_the_network_before_installing():
    with open(os.path.join(IMAGE, 'entrypoint.sh')) as f:
        text = f.read()
    assert text.index('wait_for_final_network') < text.index('install_missing_tools\n')


INSTALLED = ('claude', 't3', 'herdr')
BUN_COMMANDS = ('codex', 'cyrus', 'playwright-mcp', 'mcp-remote', 'eas', 'teamclaude')


def executable(path, body='#!/bin/sh\n'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    path.chmod(0o755)


def bun_calls(tmp_path, bun_commands):
    """install_missing_tools with Bun and `bun_commands` in ~/.bun/bin -> what it asked Bun to do."""
    for name in INSTALLED:
        executable(tmp_path / 'bin' / name)
    executable(tmp_path / '.bun' / 'bin' / 'bun', f'#!/bin/sh\necho "$*" >> {tmp_path}/bun-calls\n')
    for name in bun_commands:
        executable(tmp_path / '.bun' / 'bin' / name)
    (tmp_path / 'logs').mkdir()
    run(tmp_path, 'install_missing_tools', {'PATH': f'{tmp_path}/bin:/usr/bin:/bin'})
    calls = tmp_path / 'bun-calls'
    return calls.read_text().splitlines() if calls.exists() else []


def test_a_start_with_every_tool_installs_nothing(tmp_path):
    assert bun_calls(tmp_path, BUN_COMMANDS) == []


def test_a_missing_tool_installs_the_bun_tools_and_trusts_their_scripts(tmp_path):
    calls = bun_calls(tmp_path, BUN_COMMANDS[:-1])
    assert calls[0].startswith('add -g @openai/codex@latest ') and '@karpeleslab/teamclaude@latest' in calls[0]
    assert calls[1] == 'pm -g trust --all'


def test_old_npm_copies_go_once_the_bun_ones_are_in(tmp_path):
    npm = tmp_path / '.npm-global'
    for pkg in ('@openai/codex', 'mcp-remote', 'left-pad'):
        (npm / 'lib' / 'node_modules' / pkg).mkdir(parents=True)
    (npm / 'bin').mkdir()
    for cmd in ('codex', 'mcp-remote', 'left-pad'):
        (npm / 'bin' / cmd).symlink_to('/dev/null')
    bun_calls(tmp_path, BUN_COMMANDS)
    assert sorted(p.name for p in (npm / 'bin').iterdir()) == ['left-pad']  # the agent's own stays
    assert not (npm / 'lib' / 'node_modules' / '@openai' / 'codex').exists()
    assert (npm / 'lib' / 'node_modules' / 'left-pad').exists()


def test_old_npm_copies_stay_while_a_bun_tool_is_missing(tmp_path):
    (tmp_path / '.npm-global' / 'bin').mkdir(parents=True)
    (tmp_path / '.npm-global' / 'bin' / 'codex').symlink_to('/dev/null')
    bun_calls(tmp_path, ())  # the fake Bun installs nothing
    assert (tmp_path / '.npm-global' / 'bin' / 'codex').is_symlink()
