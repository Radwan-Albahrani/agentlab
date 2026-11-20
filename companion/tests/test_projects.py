"""Where a new chat starts: work projects only, every route saying why (bot/projects.py)."""

import pytest
from bot import projects
from bot import t3db as t3db_module
from bot.t3db import Project, Thread
from conftest import set_settings
from sqlalchemy.exc import OperationalError

PROJECTS = [
    ('p1', 'Netzero Platform', '/workspace/netzero-platform'),
    ('p2', 'node-api', '/workspace/netzero-platform/apps/node-api'),
    ('p3', 'frontend', '/workspace/netzero-platform/apps/frontend'),
    ('p4', 'companion companion', '/workspace/companions/companion'),  # the companion's own folder (its NAME)
    ('p5', 'No project', '/workspace'),
]
THREADS = [
    ('p2', 'Report timeout in allocated report', ['netzerosa/platform']),
    ('p2', 'Allocated report slow query', []),
    ('p3', 'Dashboard chart tooltip', []),
    ('p3', 'Dashboard chart legend', []),
    ('p4', 'Merge the companion template', []),
    ('p4', 'Report the template merge', []),
    *[
        ('p1', f'Chore {w}', [])
        for w in ['alpha', 'bravo', 'charlie', 'delta', 'echo', 'foxtrot', 'golf', 'hotel', 'india', 'juliet', 'kilo']
    ],
]  # enough chats that a word in a few of them is not "common"


@pytest.fixture
def t3db(t3_rows):
    t3_rows.add_all(Project(project_id=p, title=t, workspace_root=root) for p, t, root in PROJECTS)
    t3_rows.add_all(
        Thread(thread_id=f't{n}', project_id=p, title=t, payload={'pullRequests': [{'repository': r} for r in rs]})
        for n, (p, t, rs) in enumerate(THREADS)
    )
    t3_rows.commit()
    set_settings({'default_project': '/workspace/netzero-platform'})
    return t3_rows


def test_each_project_has_a_kind():
    assert projects.kind_of('node-api', '/workspace/netzero-platform/apps/node-api') == 'work'
    assert projects.kind_of('leafy companion', '/workspace/companions/leafy') == 'home'
    assert projects.kind_of('No project', '/workspace') == 'none'
    assert projects.kind_of('x', '/workspace/') == 'none'


def test_the_companions_own_name_never_routes_to_its_own_folder(t3db):
    r = projects.route('task', '@Companion why is the companion report slow?', 'Companion: looking')
    assert r['project'] != '/workspace/companions/companion'
    assert {p['root'] for p in projects._profiles().values()} == {
        '/workspace/netzero-platform',
        '/workspace/netzero-platform/apps/node-api',
        '/workspace/netzero-platform/apps/frontend',
    }


def test_a_named_project_wins_and_says_so(t3db):
    r = projects.route('task', 'Companion, check the node-api timeout', '', 'general')
    assert r == projects.made('/workspace/netzero-platform/apps/node-api', 'named', 'the ask names "node-api"')


def test_the_channel_thread_and_topic_each_route_with_their_reason(t3db):
    assert projects.route('task', 'look at this', '', 'frontend-team')['by'] == 'channel'
    assert projects.route('task', 'look at this', 'Ali: the frontend build broke', 'general')['by'] == 'thread'
    topic = projects.route('task', 'the allocated report is slow again')
    assert (topic['project'], topic['by']) == ('/workspace/netzero-platform/apps/node-api', 'topic')


def test_nothing_named_goes_to_the_default_work_project(t3db):
    assert projects.route('task', 'what do you think?') == projects.made(
        '/workspace/netzero-platform', 'default', 'nothing named a project'
    )
    assert projects.route('errand', 'invoices from node-api')['by'] == 'default'  # paperwork is not read for one


def test_a_default_set_to_a_companion_folder_is_not_used(t3db):
    set_settings({'default_project': '/workspace/companions/companion'})
    assert projects.route('task', 'hello')['project'] == '/workspace/netzero-platform'


def test_a_review_goes_to_its_repositorys_project_or_a_checkout(t3db):
    assert projects.route('review', repo='NetzeroSA/platform') == projects.made(
        '/workspace/netzero-platform/apps/node-api', 'repo', 'NetzeroSA/platform'
    )
    other = projects.route('review', repo='someone/else')
    assert (other['project'], other['by']) == ('/workspace/netzero-platform', 'checkout')


def test_an_unreadable_t3_still_routes_to_the_default(monkeypatch):
    def broken():
        raise OperationalError('select', {}, Exception('database is locked'))

    monkeypatch.setattr(t3db_module, 'engine', broken)
    r = projects.route('task', 'node-api')
    assert (r['by'], r['why']) == ('default', 'T3 unreadable (OperationalError)')


def test_unknown_routes_and_purposes_are_refused():
    with pytest.raises(ValueError):
        projects.made('/workspace/x', 'guess', '')
    with pytest.raises(ValueError):
        projects.route('chat')
