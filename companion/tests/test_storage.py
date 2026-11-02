"""The companion's memory and what the hub reads (the contract in companion.py)."""

import json
import os
import time

from bot import config, publish, state
from conftest import COMPANION_DIR


def test_save_writes_only_the_task_that_changed():
    a = state.new_task('C1', '1.1', 'T1', 'First', 'f1', '1.1', None)
    state.new_task('C1', '2.1', 'T2', 'Second', 'f2', '2.1', None)
    db = config.COMP.db
    before = db.execute('select max(updated) from store').fetchone()[0]
    time.sleep(0.01)
    a['title'] = 'First (edited)'
    state.save()
    changed = db.execute('select key from store where updated > ?', (before,)).fetchall()
    assert changed == [('task:C1:1.1',)]


def test_the_page_gets_a_heartbeat_settings_schema_and_task_cards():
    state.new_task('C1', '3.1', 'T3', 'Check the queue', 'f3', '3.1', None)
    publish.tick()
    with open(os.path.join(COMPANION_DIR, 'heartbeat.json')) as f:
        heartbeat = json.load(f)
    with open(os.path.join(COMPANION_DIR, 'settings-schema.json')) as f:
        schema = json.load(f)
    assert heartbeat['name'] == 'companion' and heartbeat['agent'] == 'agent' and heartbeat['mode'] == 'tag'
    assert [field['key'] for field in schema] == [
        'mode',
        'auto_retry',
        'github_user',
        'qa_evidence_repo',
        'publish_channel',
    ]
    row = config.COMP.db.execute("select title, status, kind from tasks where id = 'C1:3.1'").fetchone()
    assert row == ('Check the queue', 'working', 'task')


def test_events_are_appended():
    before = config.COMP.db.execute('select count(*) from events').fetchone()[0]
    config.COMP.event('sent', 'Message to Salah', to='Salah', detail='Here you go')
    assert config.COMP.db.execute('select count(*) from events').fetchone()[0] == before + 1


def test_a_card_reflects_what_the_task_waits_for():
    t = {'title': 'x', 'active': True, 'approval': {'decided': ''}, 'requester': None}
    assert publish.card('k', t)['status'] == 'waiting'
    t['approval']['decided'] = 'approved'
    assert publish.card('k', t)['status'] == 'working'
    t.update(active=False, outcome='failed')
    assert publish.card('k', t)['status'] == 'failed'
