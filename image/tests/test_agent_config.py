import tomllib

import pytest
from conftest import load_script

agent_config = load_script('agent-config')
BROWSER = '/usr/local/bin/browser-mcp-lazy'


def test_fresh_config_gets_file_credentials_and_the_browser_tool():
    config = tomllib.loads(agent_config.codex_with_browser('', BROWSER))
    assert config['cli_auth_credentials_store'] == 'file'
    assert config['mcp_servers']['playwright'] == {
        'command': BROWSER,
        'args': [],
        'env': {'DISPLAY': ':99'},
        'startup_timeout_sec': 60,
    }


def test_older_entries_are_replaced_and_other_blocks_kept():
    old = (
        'cli_auth_credentials_store = "file"\nmodel = "gpt-5"\n\n'
        '[mcp_servers.playwright]\ncommand = "/old/playwright"\n\n'
        '[mcp_servers.playwright.env]\nX = "1"\n\n'
        '# BEGIN agent-connections (managed by the Accounts page; edits are overwritten)\n'
        '[mcp_servers.linear]\ncommand = "mcp-remote"\n\n# END agent-connections\n'
    )
    once = agent_config.codex_with_browser(old, BROWSER)
    twice = agent_config.codex_with_browser(once, BROWSER)
    assert once == twice  # idempotent across restarts
    config = tomllib.loads(once)
    assert config['model'] == 'gpt-5' and config['mcp_servers']['linear']['command'] == 'mcp-remote'
    assert config['mcp_servers']['playwright']['command'] == BROWSER
    assert once.count('[mcp_servers.playwright]') == 1 and 'BEGIN agent-connections' in once


def test_invalid_toml_is_never_written(tmp_path):
    path = tmp_path / 'config.toml'
    path.write_text('this is = = not toml\n')
    with pytest.raises(tomllib.TOMLDecodeError):
        agent_config.write_codex(str(path), BROWSER)
    assert path.read_text() == 'this is = = not toml\n'


def instructions(tmp_path, monkeypatch, text):
    path = tmp_path / 'instructions.md'
    path.write_text(text)
    monkeypatch.setattr(agent_config, 'INSTRUCTIONS', str(path))


def test_notes_are_told_once_and_agent_files_are_kept(tmp_path, monkeypatch):
    instructions(
        tmp_path, monkeypatch, 'Your environment (agent: {{AGENT_ID}})\n<!-- android -->\nAndroid\n<!-- /android -->\n'
    )
    (tmp_path / '.claude').mkdir()
    (tmp_path / '.claude' / 'CLAUDE.md').write_text('# my own memories\n')
    agent_config.write_notes('example', str(tmp_path))
    agent_config.write_notes('example', str(tmp_path))
    claude = (tmp_path / '.claude' / 'CLAUDE.md').read_text()
    assert claude.startswith('# my own memories\n') and claude.count('@') == 1
    agents = (tmp_path / '.codex' / 'AGENTS.md').read_text()
    assert agents.count('agent: example') == 1 and 'Android' not in agents


def test_companions_section_names_them_and_is_dropped_without_any(tmp_path, monkeypatch):
    instructions(tmp_path, monkeypatch, 'a\n<!-- companions -->\nYours: {{COMPANIONS}}\n<!-- /companions -->\nb\n')
    notes = tmp_path / '.config' / 'agent' / 'environment.md'
    agent_config.write_notes('example', str(tmp_path), companions=['helper', 'scout'])
    assert notes.read_text() == 'a\nYours: helper, scout\nb\n'
    agent_config.write_notes('example', str(tmp_path))
    assert notes.read_text() == 'a\nb\n'


def test_android_section_is_kept_only_when_enabled(tmp_path, monkeypatch):
    instructions(tmp_path, monkeypatch, 'top\n<!-- android -->\nAndroid\n<!-- /android -->\nend\n')
    agent_config.write_notes('example', str(tmp_path), android=True)
    assert (tmp_path / '.config' / 'agent' / 'environment.md').read_text() == 'top\nAndroid\nend\n'


OLD_BEGIN = '<!-- BEGIN agent-environment (managed by the container; edits here are overwritten) -->'
OLD_END = '<!-- END agent-environment -->'


@pytest.mark.parametrize(
    ('before', 'after', 'nl'),
    [
        ('', '\n# my memories\n- likes tabs\n', '\n'),
        ('# notes first\r\n', '\r\nmine\r\n', '\r\n'),  # CRLF file: endings kept everywhere
        ('', '\nno trailing newline', '\n'),
    ],
)
def test_only_the_marked_block_is_replaced(tmp_path, monkeypatch, before, after, nl):
    instructions(tmp_path, monkeypatch, 'Current notes for {{AGENT_ID}}\nsecond line\n')
    stale = nl.join([OLD_BEGIN, 'stale line 1', 'stale line 2', OLD_END])
    for rel in ('.claude/CLAUDE.md', '.codex/AGENTS.md'):
        (tmp_path / rel).parent.mkdir(exist_ok=True)
        (tmp_path / rel).write_bytes((before + stale + after).encode())
    agent_config.write_notes('example', str(tmp_path))
    agent_config.write_notes('example', str(tmp_path))  # a second start changes nothing more
    for rel, body in (
        ('.claude/CLAUDE.md', f'@{tmp_path}/.config/agent/environment.md'),
        ('.codex/AGENTS.md', 'Current notes for example' + nl + 'second line'),
    ):
        data = (tmp_path / rel).read_bytes().decode()
        assert data.startswith(before) and data.endswith(after), rel  # every byte outside the block kept
        inner = data[len(before) : len(data) - len(after)]
        assert inner == nl.join([agent_config.BLOCK_BEGIN, body, OLD_END]), rel
        assert 'stale' not in data


def test_a_file_without_a_complete_block_is_left_alone(tmp_path, monkeypatch):
    instructions(tmp_path, monkeypatch, 'Current notes\n')
    (tmp_path / '.claude').mkdir()
    half = f'mine\n{OLD_BEGIN}\nno end marker\n'
    (tmp_path / '.claude' / 'CLAUDE.md').write_text(half)
    agent_config.write_notes('example', str(tmp_path))
    assert (tmp_path / '.claude' / 'CLAUDE.md').read_text() == half


def test_a_new_file_gets_a_marked_block_it_can_refresh_later(tmp_path, monkeypatch):
    instructions(tmp_path, monkeypatch, 'v1\n')
    agent_config.write_notes('example', str(tmp_path))
    agents = tmp_path / '.codex' / 'AGENTS.md'
    agents.write_text(agents.read_text() + '\n# the agent wrote this\n')
    instructions(tmp_path, monkeypatch, 'v2\n')
    agent_config.write_notes('example', str(tmp_path))
    text = agents.read_text()
    assert 'v2' in text and 'v1' not in text and text.endswith('\n# the agent wrote this\n')
