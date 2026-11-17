import json
import os
import tomllib

import pool

CODEX = """cli_auth_credentials_store = "file"

# BEGIN agent-builtin (written by the container entrypoint on every start)
[mcp_servers.playwright]
command = "/usr/local/bin/browser-mcp-lazy"
# END agent-builtin
"""


def test_a_provider_is_routed_while_it_has_an_enabled_account():
    accts = [
        {'name': 'a', 'provider': 'claude', 'disabled': False},
        {'name': 'b', 'provider': 'codex', 'disabled': True},
    ]
    assert pool.wanted(accts) == (True, False)
    assert pool.wanted([]) == (False, False)


def test_seed_keeps_teamclaudes_own_settings_and_accounts():
    config = {'proxy': {'apiKey': 'tc-x', 'port': 9}, 'accounts': [{'name': 'a'}], 'quotaProbeSeconds': 0}
    seeded, changed = pool.seed_config(config)
    assert changed
    assert seeded['proxy'] == {'apiKey': 'tc-x', 'port': 3456, 'host': '127.0.0.1', 'cliproxyApi': 'read'}
    assert seeded['quotaProbeSeconds'] == 0  # the owner's choice stays
    assert seeded['poolQuotaHeaders'] is True
    assert seeded['accounts'] == [{'name': 'a'}]
    assert pool.seed_config(seeded) == (seeded, False)


def test_claude_is_pointed_at_the_pool_and_back():
    on = pool.claude_settings({'model': 'opus'}, True)
    assert on == {'model': 'opus', 'env': {'ANTHROPIC_BASE_URL': pool.URL}}
    assert pool.claude_settings(on, True) is None
    assert pool.claude_settings(on, False) == {'model': 'opus'}


def test_claude_keeps_a_base_url_the_owner_set():
    mine = {'env': {'ANTHROPIC_BASE_URL': 'https://gateway.example'}}
    assert pool.claude_settings(mine, True) is None
    assert pool.claude_settings(mine, False) is None


def test_codex_gets_a_provider_and_loses_it_again():
    on = pool.codex_config(CODEX, True)
    parsed = tomllib.loads(on)
    assert parsed['model_provider'] == pool.PROVIDER
    assert parsed['model_providers'][pool.PROVIDER]['base_url'] == f'{pool.URL}/backend-api/codex'
    assert parsed['mcp_servers']['playwright']['command'] == '/usr/local/bin/browser-mcp-lazy'
    assert pool.codex_config(on, True) is None
    off = pool.codex_config(on, False)
    assert tomllib.loads(off) == tomllib.loads(CODEX)
    assert pool.codex_config(off, False) is None


def test_codex_keeps_a_provider_the_owner_chose():
    mine = 'model_provider = "azure"\n' + CODEX
    assert pool.codex_config(mine, True) is None


def test_t3_shows_the_pool_as_a_usage_source_only_while_it_runs():
    on = pool.t3_settings({'defaultRuntimeMode': 'auto'}, True, 'tc-x')
    src = on['usageLimitSources'][pool.T3_SOURCE]
    assert (src['kind'], src['url'], src['managementKey']) == ('cliproxy', pool.URL, 'tc-x')
    assert pool.t3_settings(on, True, 'tc-x') is None
    assert pool.t3_settings(on, False) == {'defaultRuntimeMode': 'auto', 'usageLimitSources': {}}


def test_rows_carry_quota_and_problems():
    status = {
        'currentAccounts': {'anthropic': 'me@x'},
        'accounts': [
            {
                'name': 'me@x',
                'type': 'oauth',
                'provider': 'anthropic',
                'status': 'active',
                'quota': {'unified5h': 0.42, 'unified5hReset': 1_800_000_000_000, 'unified7d': 0.1},
            },
            {'name': 'old@x', 'type': 'oauth', 'provider': 'anthropic', 'status': 'error', 'errorReason': {'detail': 'gone'}},
        ],
    }
    rows = [pool._row(a, status['currentAccounts']) for a in status['accounts']]
    assert rows[0]['provider'] == 'claude'
    assert rows[0]['current'] and rows[0]['windows'][0] == {'label': '5 hours', 'used': 42.0, 'resetsAt': 1_800_000_000}
    assert rows[0]['windows'][1]['resetsAt'] is None
    assert (rows[1]['current'], rows[1]['problem'], rows[1]['windows']) == (False, 'gone', [])


def test_sync_leaves_an_unreadable_claude_settings_file_alone(monkeypatch, tmp_path):
    for name in ('CONFIG', 'CLAUDE_SETTINGS', 'CODEX_CONFIG', 'T3_SETTINGS'):
        monkeypatch.setattr(pool, name, str(tmp_path / name.lower()))
    monkeypatch.setattr(pool, 'T3_SETTINGS', str(tmp_path / 'no-t3' / 'settings.json'))
    monkeypatch.setattr(pool, '_supervise', lambda on: None)
    (tmp_path / 'config').write_text(json.dumps({'accounts': [{'name': 'a', 'type': 'oauth'}]}))
    (tmp_path / 'claude_settings').write_text('{broken')
    pool.sync()
    assert (tmp_path / 'claude_settings').read_text() == '{broken'
    assert not os.path.exists(tmp_path / 'codex_config')  # no Codex account: nothing to route
    assert json.loads((tmp_path / 'config').read_text())['proxy']['port'] == 3456
    assert not os.path.exists(tmp_path / 'no-t3')  # T3 not installed (no userdata folder)
