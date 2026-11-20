import json
import os
import time

from bot import config, ledger, machine, projects, prompts, publish, state
from conftest import COMPANION_DIR, ROUTE, set_settings
from sqlalchemy import func, select
from tables import Event, Item, Stored, TaskCard


def test_save_writes_only_the_task_that_changed():
    a = state.new_task('C1', '1.1', 'T1', 'First', 'f1', '1.1', None, ROUTE)
    state.new_task('C1', '2.1', 'T2', 'Second', 'f2', '2.1', None, ROUTE)
    with config.COMP.session() as s:
        before = s.scalar(select(func.max(Stored.updated)))
    time.sleep(0.01)
    a['title'] = 'First (edited)'
    state.save()
    with config.COMP.session() as s:
        changed = list(s.scalars(select(Stored.key).where(Stored.updated > before)))
    assert changed == ['task:C1:1.1']


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
    with config.COMP.session() as s:
        row = s.get_one(TaskCard, 'C1:3.1')
    assert (row.title, row.status, row.kind, row.party, row.phase) == (
        'Check the queue',
        'working',
        'task',
        'owner',
        'working',
    )


def events():
    with config.COMP.session() as s:
        return s.scalar(select(func.count()).select_from(Event))


def test_events_are_appended():
    before = events()
    config.COMP.event('sent', 'Message to Salah', to='Salah', detail='Here you go')
    assert events() == before + 1


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
    with config.COMP.session() as s:
        row = s.scalars(select(Item).where(Item.task == 'C1:5.1')).one()
    assert (row.kind, row.state, row.seq) == ('message', 'sent', 1)
    data = row.data
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
