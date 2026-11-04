import json

import onboarding
import pairing
import pytest


@pytest.fixture
def signed_in(monkeypatch, tmp_path):
    state = {'claude': False, 'codex': False, 'github': False}
    monkeypatch.setattr(onboarding.signin, 'status', lambda flow, fresh=False: (state[flow], ''))
    monkeypatch.setattr(onboarding.connectors, 'load', dict)
    monkeypatch.setattr(onboarding, 'MARK', str(tmp_path / 'onboarded'))
    return state


def test_finish_needs_an_ai_sign_in_and_done_needs_the_finish(signed_in):
    assert onboarding.finish() == 'Sign in to Claude Code or Codex first.'
    assert onboarding.state()['done'] is False
    signed_in['codex'] = True
    st = onboarding.state()
    assert (st['ready'], st['done']) == (True, False)
    assert [s['id'] for s in st['steps']] == ['claude', 'codex', 'connectors', 'github']
    assert onboarding.finish() == ''
    assert onboarding.state()['done'] is True
    signed_in['codex'] = False
    assert onboarding.state()['done'] is False


@pytest.fixture
def t3(monkeypatch):
    calls = []
    replies = {}

    def run(cmd, timeout=20):
        calls.append(cmd)
        return next((v for k, v in replies.items() if cmd.startswith(k)), (1, 'unknown'))

    monkeypatch.setattr(pairing, 'run', run)
    monkeypatch.setenv('AGENTLAB_DOMAIN', 'agents.example.com')
    monkeypatch.setenv('AGENTLAB_PAIR_HOST', '')
    monkeypatch.setenv('AGENTLAB_AUTH_MODE', 'cloudflare-access')
    monkeypatch.setenv('AGENTLAB_PUBLISHED', '')
    return calls, replies


def made(token='tok123'):
    return 0, json.dumps({'id': 'p1', 'token': token, 'expiresAt': '2026-01-01T00:05:00Z'})


def test_browser_link_is_on_the_cluster_domain(t3):
    calls, replies = t3
    replies['t3 auth pairing create'] = made()
    out = pairing.pair('browser', 'my laptop')
    assert out['available'] and out['url'] == 'https://agents.example.com/pair#token=tok123'
    assert "--ttl 5m --label 'my laptop' --base-url 'https://agents.example.com'" in calls[0]


def test_app_needs_a_pair_host_except_on_a_tailnet(t3, monkeypatch):
    calls, replies = t3
    replies['t3 auth pairing create'] = made()
    assert pairing.pair('app', 'phone')['available'] is False and not calls
    monkeypatch.setenv('AGENTLAB_PAIR_HOST', 'sara-t3.example.com')
    out = pairing.pair('app', 'phone')
    assert out['url'] == 'https://sara-t3.example.com/pair#token=tok123' and '--ttl 10m' in calls[0]
    monkeypatch.setenv('AGENTLAB_PAIR_HOST', '')
    monkeypatch.setenv('AGENTLAB_AUTH_MODE', 'tailscale')
    assert pairing.pair('app', 'phone')['url'].startswith('https://agents.example.com/pair#token=')


def test_published_t3_links_use_the_hub_pages_host_and_the_port(t3, monkeypatch):
    calls, replies = t3
    replies['t3 auth pairing create'] = made()
    monkeypatch.setenv('AGENTLAB_PUBLISHED', 't3=7101,browser=7103')
    for kind in ('browser', 'app'):
        out = pairing.pair(kind, 'phone', 'Homebox.Tailnet.ts.net')
        assert out['url'] == 'http://homebox.tailnet.ts.net:7101/pair#token=tok123'
    assert "--base-url 'http://homebox.tailnet.ts.net:7101'" in calls[-1]
    for bad in ('evil.com:80', 'evil.com/x', 'a b', "x';rm", ''):
        assert pairing.pair('browser', '', bad)['url'].startswith('https://agents.example.com/')
    monkeypatch.setenv('AGENTLAB_PUBLISHED', '')
    assert pairing.pair('browser', '', 'homebox')['url'].startswith('https://agents.example.com/')


def test_unknown_kind_and_t3_failure(t3):
    with pytest.raises(ValueError):
        pairing.pair('tv', '')
    assert pairing.pair('browser', '')['available'] is False


def test_devices_are_paired_sessions_only_and_revoke_checks_ownership(t3):
    calls, replies = t3
    sessions = [
        {'sessionId': 'd1', 'subject': 'one-time-token', 'client': {'label': 'phone', 'ipAddress': '10.0.0.5'}},
        {'sessionId': 'b1', 'subject': 'mcp-client', 'client': {'label': 'companion answer'}},
    ]
    replies['t3 auth session list'] = (0, json.dumps(sessions))
    replies['t3 auth session revoke'] = (0, '')
    assert [d['id'] for d in pairing.devices()] == ['d1']
    assert pairing.revoke('b1') == pairing.NO_DEVICE
    assert pairing.revoke('d1') == '' and calls[-1] == "t3 auth session revoke 'd1'"
