import json
import os
import time

from bot import config, ledger, machine, projects, prompts, publish, state
from conftest import COMPANION_DIR, ROUTE, set_settings


def test_save_writes_only_the_task_that_changed():
    a = state.new_task('C1', '1.1', 'T1', 'First', 'f1', '1.1', None, ROUTE)
    state.new_task('C1', '2.1', 'T2', 'Second', 'f2', '2.1', None, ROUTE)
    db = config.COMP.db
    before = db.execute('select max(updated) from store').fetchone()[0]
    time.sleep(0.01)
    a['title'] = 'First (edited)'
    state.save()
    changed = db.execute('select key from store where updated > ?', (before,)).fetchall()
    assert changed == [('task:C1:1.1',)]


def test_the_page_gets_a_heartbeat_settings_schema_and_task_cards():
    machine.begin_turn(
        state.new_task('C1', '3.1', 'T3', 'Check the queue', 'f3', '3.1', None, ROUTE), 'owner', 'thread'
    )
    publish.tick()
    with open(os.path.join(COMPANION_DIR, 'heartbeat.json')) as f:
        heartbeat = json.load(f)
    with open(os.path.join(COMPANION_DIR, 'settings-schema.json')) as f:
        schema = json.load(f)
    assert heartbeat['name'] == 'companion' and heartbeat['agent'] == 'agent' and heartbeat['mode'] == 'tag'
    assert [p['name'] for p in heartbeat['people']] == ['Ali', 'Ali Khan']
    assert [field['key'] for field in schema] == [
        'mode',
        'access',
        'auto_retry',
        'org',
        'default_project',
        'github_user',
        'qa_evidence_repo',
        'review_slots',
        'review_requests',
        'github_people',
        'publish_channel',
        'requests_channel',
    ]
    row = config.COMP.db.execute("select title, status, kind, party, phase from tasks where id = 'C1:3.1'").fetchone()
    assert row == ('Check the queue', 'working', 'task', 'owner', 'working')


def test_events_are_appended():
    before = config.COMP.db.execute('select count(*) from events').fetchone()[0]
    config.COMP.event('sent', 'Message to Salah', to='Salah', detail='Here you go')
    assert config.COMP.db.execute('select count(*) from events').fetchone()[0] == before + 1


def test_a_card_reflects_the_phase_and_what_the_task_waits_for():
    t = state.new_task('C1', '4.1', 'T4', 'x', 'f4', '4.1', None, ROUTE)
    machine.begin_turn(t, 'owner', 'thread')
    a = ledger.add(t, 'approval', action='Merge')
    ledger.move(t, a, 'awaiting_owner')
    card = publish.card('k', t)
    assert (card['status'], card['phase'], card['waiting']) == ('waiting', 'waiting_owner', 'approval')
    ledger.move(t, a, 'approved')
    assert (publish.card('k', t)['status'], publish.card('k', t)['waiting']) == ('working', '')
    machine.end_turn(t, 'failed')
    assert (publish.card('k', t)['status'], publish.card('k', t)['phase']) == ('failed', 'failed')


def test_the_ledger_is_published_for_the_hub():
    t = state.new_task('C1', '5.1', 'T5', 'x', 'f5', '5.1', None, ROUTE)
    machine.begin_turn(t, 'owner', 'thread')
    it = ledger.add(t, 'message', to='colleague', label='Salah', text='On it.')
    ledger.move(t, it, 'sent')
    publish._last = 0.0
    publish.tick()
    row = config.COMP.db.execute("select kind, state, seq, data from items where task = 'C1:5.1'").fetchone()
    assert row[:3] == ('message', 'sent', 1)
    data = json.loads(row[3])
    assert data['label'] == 'Salah' and [h[0] for h in data['history']] == ['received', 'sent']


def test_where_the_owner_works_and_the_default_project_are_live_settings(monkeypatch):
    monkeypatch.setattr(projects, '_profiles', dict)
    assert projects.route('errand')['project'] == '/workspace'
    set_settings({'org': 'Example Co', 'default_project': '/workspace/app'})
    assert config.org() == 'Example Co'
    assert projects.route('errand') == projects.made('/workspace/app', 'default', 'nothing named a project')
    t = state.new_task('C9', '9.3', 'T9', 'Named', 'f9', '9.3', None, projects.made('/workspace/x', 'named', 'x'))
    assert t['route'] == {'project': '/workspace/x', 'by': 'named', 'why': 'x'} and 'project' not in t
    assert 'outside Example Co' in prompts.approvals('Sam', 'Ali', 'tell Ali')
    errand = prompts.errand('Ali', 'wrote', 'Sam', 'add me to the dashboard', [], [], '/files/x')
    assert errand.index('connected (MCP) tools') < errand.index("Needs Sam's OK first")
    keys = [s['key'] for s in config.SCHEMA]
    assert {'org', 'default_project'} <= set(keys)
