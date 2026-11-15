import json
import os
import subprocess

IMAGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(IMAGE, 'use-t3-threads')


def run(env):
    return subprocess.run(
        ['sh', HOOK], input='{"tool_name": "Agent"}', capture_output=True, text=True, env=env, check=False
    )


def test_in_a_t3_chat_a_builtin_subagent_is_turned_into_a_t3_child_thread():
    r = run({'PATH': os.environ['PATH'], 'T3CODE_THREAD_ID': 'mcp:abc'})
    assert r.returncode == 2  # blocks the call; stderr goes back to Claude
    assert 'mcp__t3-code__delegate_task' in r.stderr


def test_outside_t3_subagents_stay_allowed():
    assert run({'PATH': os.environ['PATH']}).returncode == 0


def test_the_policy_hooks_the_agent_tools_to_it():
    with open(os.path.join(IMAGE, 'claude-managed-settings.json')) as f:
        hook = json.load(f)['hooks']['PreToolUse'][0]
    assert hook['matcher'] == '^(Agent|Task)$'
    assert hook['hooks'][0]['command'] == '/usr/local/bin/use-t3-threads'
