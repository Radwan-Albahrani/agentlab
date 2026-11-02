import pytest
import util


@pytest.fixture(autouse=True)
def cluster(monkeypatch):
    monkeypatch.setenv('AGENTLAB_DOMAIN', 'agents.example.com')
    monkeypatch.setenv('AGENTLAB_HUB_DOMAIN', 'agents-hub.example.com')


@pytest.mark.parametrize(
    ('app', 'url'),
    [
        ('t3', 'https://agents.example.com'),
        ('accounts', 'https://agents.example.com/_agentlab/accounts'),
        ('browser', 'https://agents.example.com/_agentlab/browser'),
        ('terminal', 'https://agents.example.com/_agentlab/terminal'),
        ('hub', 'https://agents-hub.example.com'),
    ],
)
def test_tools_live_under_paths_of_the_one_domain(app, url):
    assert util.public_url(app, 'ignored.example.org') == url


def test_without_env_the_opened_host_stands_in(monkeypatch):
    monkeypatch.delenv('AGENTLAB_DOMAIN')
    monkeypatch.delenv('AGENTLAB_HUB_DOMAIN')
    assert util.public_url('browser', 'localhost:8088', 'http') == 'http://localhost:8088/_agentlab/browser'
    assert util.public_url('hub', 'localhost') == ''
    assert util.public_url('t3') == ''
