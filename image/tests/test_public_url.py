import pytest
import util


@pytest.fixture(autouse=True)
def cluster(monkeypatch):
    monkeypatch.setenv('AGENTLAB_DOMAIN', 'agents.example.com')
    monkeypatch.setenv('AGENTLAB_HUB_DOMAIN', 'agents-hub.example.com')
    monkeypatch.delenv('AGENTLAB_PUBLISHED', raising=False)
    monkeypatch.delenv('AGENTLAB_PUBLISHED_HUB', raising=False)


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


def test_published_tools_use_the_opened_host_and_their_port(monkeypatch):
    monkeypatch.setenv('AGENTLAB_PUBLISHED', 't3=7101,accounts=7102,browser=7103,terminal=7104')
    monkeypatch.setenv('AGENTLAB_PUBLISHED_HUB', '7190')
    assert util.public_url('hub', 'HomeBox:7102') == 'http://homebox:7190'
    assert util.public_url('browser', 'homebox:7102') == 'http://homebox:7103'
    assert util.public_url('terminal', 'homebox') == 'http://homebox:7104/_agentlab/terminal'
    # An odd Host header never ends up in a link: the cluster's own address is used instead.
    assert util.public_url('hub', '[::1]:7102') == 'https://agents-hub.example.com'
    monkeypatch.setenv('AGENTLAB_PUBLISHED_HUB', '')
    assert util.public_url('hub', 'homebox:7102') == 'https://agents-hub.example.com'
