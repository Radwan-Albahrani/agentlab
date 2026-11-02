import signin

GH_SCREEN = """! Opt in to expiring, auto-refreshing OAuth tokens: https://github.blog/changelog/2026-10-21-github-cli-opt-in-to-expiring-auto-refreshing-oauth-tokens/

! First copy your one-time code: AB12-CD34
Open this URL to continue in your web browser: https://github.com/login/device
"""


def flow_screen(monkeypatch, scr):
    monkeypatch.setattr(signin, 'status', lambda flow, fresh=False: (False, ''))
    monkeypatch.setattr(signin, 'active', lambda flow: True)
    monkeypatch.setattr(signin, 'screen', lambda flow: scr)
    monkeypatch.setattr(signin, 'mode', lambda flow: 'default')


def test_github_link_is_the_device_page_not_an_announcement(monkeypatch):
    flow_screen(monkeypatch, GH_SCREEN)
    st = signin.state('github')
    assert (st['url'], st['code']) == ('https://github.com/login/device', 'AB12-CD34')


def test_no_link_until_gh_prints_the_device_page(monkeypatch):
    flow_screen(monkeypatch, GH_SCREEN.split('\n\n', 1)[0])
    assert signin.state('github')['url'] == ''


def test_other_flows_take_the_first_link(monkeypatch):
    flow_screen(monkeypatch, 'Visit https://auth.openai.com/codex/device.\nCode: WXYZ-1234')
    assert signin.state('codex')['url'] == 'https://auth.openai.com/codex/device'
