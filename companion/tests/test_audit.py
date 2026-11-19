"""Every task says who started it, how, and who approved it: the hub's audit (publish.card)."""

import sqlite3

import pytest
from bot import errands, inbox, projects, publish, routing, slack, state, t3, tasks
from bot.state import key
from conftest import OWNER, ROUTE, set_settings

from companion import Companion


@pytest.fixture
def chats(t3_quiet, monkeypatch):
    monkeypatch.setattr(projects, '_profiles', dict)
    monkeypatch.setattr(slack, 'thread_messages', lambda ch, tts, ts: [])
    return t3_quiet


def audit_of(ch, ts):
    k = key(ch, ts)
    c = publish.card(k, state.state['tasks'][k])
    return c['started_by'], c['via'], c['approved_by']


def test_the_owners_own_tasks_are_theirs(chats):
    tasks.start('D_OWNER', '10.1', '10.1', 'check the queue')
    tasks.start('C_RANDOM', '11.1', '11.1', '<@BCOMPANION> fix it')
    assert audit_of('D_OWNER', '10.1') == ('', 'in a DM', '')
    assert audit_of('C_RANDOM', '11.1') == ('', 'in #general', '')


def test_a_colleague_with_access_is_named(chats):
    set_settings({'access': ['U_SALAH']})
    routing.route(
        {'channel': 'C1', 'ts': '12.1', 'user': 'U_SALAH', 'text': '<@BCOMPANION> make the logo bigger'}, True
    )
    assert audit_of('C1', '12.1') == ('Salah', 'in #general', '')
    assert publish.card(key('C1', '12.1'), state.state['tasks'][key('C1', '12.1')])['requester'] == 'Salah'


def test_an_approved_request_names_who_asked_where_and_who_approved(chats):
    set_settings({'requests_channel': 'C_REQ'})
    state.state.pop('inbox', None)
    routing.route(
        {'channel': 'C_REQ', 'ts': '13.1', 'user': 'U_SALAH', 'text': '<@BCOMPANION> rename the report'}, True
    )
    inbox.decide(key('C_REQ', '13.1'), True)
    assert audit_of('C_REQ', '13.1') == ('Salah', 'in the requests channel #general', 'Sam')


def test_an_errand_is_for_the_colleague_and_started_by_whoever_triggered_it(chats, monkeypatch):
    monkeypatch.setattr(t3, 'start_thread', lambda project, title, message: ('T_E', ''))
    p = {'ch': 'C1', 'ts': '14.1', 'thread_ts': None, 'user': 'U_SALAH', 'im': False, 'texts': ['the invoices']}
    errands.track(dict(p, tagged=True), 'D_OWNER', '14.2', 'T_E', 'Salah: invoices', 'f', '', ROUTE)
    errands.track(p, 'D_OWNER', '14.3', 'T_E', 'Salah: invoices', 'f', '', ROUTE)
    tagged = publish.card('a', state.state['tasks'][key('D_OWNER', '14.2')])
    noticed = publish.card('b', state.state['tasks'][key('D_OWNER', '14.3')])
    assert (tagged['kind'], tagged['requester'], tagged['started_by'], tagged['via']) == (
        'errand',
        'Salah',
        '',
        'by your tag on their message',
    )
    assert (noticed['started_by'], noticed['via']) == ('Salah', 'noticed in team mode')


def test_an_older_database_gets_the_audit_columns(tmp_path):
    con = sqlite3.connect(tmp_path / 'companion.db')
    con.execute(
        'create table tasks (id text primary key, title text, kind text, requester text, status text, '
        'waiting text, outcome text, started text, ended text, thread text, slack text, source text, '
        'updated real)'
    )
    con.commit()
    con.close()
    comp = Companion('x', 'agent', str(tmp_path))
    comp.tasks([{'id': 't', 'title': 'x', 'started_by': 'Salah', 'via': 'in a DM', 'approved_by': 'Sam'}])
    row = comp.db.execute('select started_by, via, approved_by from tasks').fetchone()
    assert row == ('Salah', 'in a DM', 'Sam')
    assert OWNER  # the owner's own work has started_by ''
