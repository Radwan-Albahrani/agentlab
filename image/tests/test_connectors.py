import hashlib
import json
import os
import tomllib

import connectors
import pytest


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(connectors, 'HOME', str(tmp_path))
    monkeypatch.setattr(connectors, 'STORE', str(tmp_path / 'mcp.json'))
    monkeypatch.setattr(connectors, 'MCP_AUTH', str(tmp_path / '.mcp-auth'))
    monkeypatch.setattr(connectors, 'run', lambda cmd, timeout=20: (0, ''))  # no claude CLI or tmux in tests
    monkeypatch.setattr(connectors, 'stop_session', lambda flow: None)
    (tmp_path / '.codex').mkdir()
    return tmp_path


def codex_config(home):
    return (home / '.codex' / 'config.toml').read_text()


def test_catalog_has_axiom_and_every_entry_is_https():
    assert connectors.CATALOG['axiom']['url'] == 'https://mcp.axiom.co/mcp'
    assert all(c['url'].startswith('https://') for c in connectors.CATALOG.values())


def test_shared_and_token_servers_render_valid_codex_config(home):
    (home / '.codex' / 'config.toml').write_text('model = "gpt"\n\n[mcp_servers.playwright]\ncommand = "x"\n')
    connectors.add_shared('linear', connectors.CATALOG['linear']['url'])
    connectors.register_token('github', connectors.GITHUB_MCP, 'Bearer t0k', '@me')
    config = tomllib.loads(codex_config(home))
    assert config['model'] == 'gpt' and config['mcp_servers']['playwright']['command'] == 'x'
    assert config['mcp_servers']['linear']['args'] == ['https://mcp.linear.app/mcp']
    assert config['mcp_servers']['github']['http_headers'] == {'Authorization': 'Bearer t0k'}


def test_block_is_replaced_not_duplicated(home):
    connectors.add_shared('sentry', connectors.CATALOG['sentry']['url'])
    connectors.add_shared('notion', connectors.CATALOG['notion']['url'])
    connectors.unregister('sentry')
    text = codex_config(home)
    assert text.count('# BEGIN agent-connections') == 1
    assert 'mcp_servers.notion' in text and 'mcp_servers.sentry' not in text


def test_servers_lists_catalog_then_custom(home):
    connectors.add_shared('myserver', 'https://mcp.example.com/mcp')
    servers = connectors.servers()
    assert list(servers)[: len(connectors.CATALOG)] == list(connectors.CATALOG)
    assert servers['myserver'] == {
        'name': 'myserver',
        'url': 'https://mcp.example.com/mcp',
        'what': 'mcp.example.com',
        'added': True,
    }
    assert servers['linear']['added'] is False


@pytest.mark.parametrize(
    ('name', 'url'),
    [('Bad', 'https://x'), ('playwright', 'https://x'), ('linear', 'https://x'), ('ok-name', 'http://insecure')],
)
def test_add_custom_validates(name, url):
    assert connectors.add_custom(name, url)


def test_signed_in_follows_the_shared_token_file(home):
    url = connectors.CATALOG['axiom']['url']
    connectors.add_shared('axiom', url)
    assert not connectors.signed_in('axiom')
    folder = home / '.mcp-auth' / 'mcp-remote-0.1'
    folder.mkdir(parents=True)
    (folder / f'{hashlib.md5(url.encode()).hexdigest()}_tokens.json').write_text(json.dumps({}))
    assert connectors.signed_in('axiom')
    connectors.remove('axiom')
    assert not os.listdir(folder)
