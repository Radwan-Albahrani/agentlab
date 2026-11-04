import json
import os
import shutil
import time

import pytest
from bot import drafts, routing, slack, state, t3
from conftest import OWNER

KEY = '2026-11-01'
POSTED_TS = f'{time.time() + 50:.6f}'  # after the uploads below, before any ready.json is stamped


@pytest.fixture
def draft(fresh_bot, monkeypatch):
    d = os.path.join(drafts.DRAFTS, KEY)
    os.makedirs(d, exist_ok=True)
    monkeypatch.setattr(drafts.time, 'sleep', lambda s: None)
    monkeypatch.setattr(t3, 'start_thread', lambda project, title, message: ('T_REV', ''))
    fresh_bot.conversations_history = lambda **kw: {
        'messages': [{'ts': POSTED_TS, 'user': 'BCOMPANION', 'files': [{'id': 'F1'}]}]
        if float(kw['oldest']) <= float(POSTED_TS)
        else []
    }
    yield d
    shutil.rmtree(d)


def write(d, text, revision):
    with open(os.path.join(d, 'update.md'), 'w', encoding='utf-8') as f:
        f.write(text)
    with open(os.path.join(d, 'shot.png'), 'wb') as f:
        f.write(b'png')
    ready = os.path.join(d, 'ready.json')
    with open(ready, 'w') as f:
        json.dump({'title': 'Weekly', 'revision': revision}, f)
    stamp = time.time() + 100 + revision
    os.utime(ready, (stamp, stamp))


def press(action, msg_ts='9.0'):
    drafts._finish(
        lambda: None,
        {'user': {'id': OWNER}, 'actions': [{'value': KEY}], 'container': {'message_ts': msg_ts}},
        action == 'draft_post',
    )


def test_image_references_are_dropped(draft, fresh_bot):
    write(draft, '**News**\n\n![Live wall](2-live-wall.png)\n\n\n![Directory](3-dir.png)\n\n• Seeds history', 1)
    drafts.tick()
    comment = fresh_bot.uploads[-1]['initial_comment']
    assert '![' not in comment
    assert comment == '*News*\n\n• Seeds history'


def test_a_reply_after_posting_edits_the_post(draft, fresh_bot):
    write(draft, 'First ![x](a.png) version', 1)
    drafts.tick()
    press('draft_post')
    st = state.state['drafts'][KEY]
    assert st['status'] == 'posted'
    assert st['posted'] == {'channel': st['posted']['channel'], 'ts': POSTED_TS, 'files': True}

    routing.route({'channel': st['dm'], 'ts': '20.0', 'thread_ts': st['thread'], 'user': OWNER, 'text': 'fix'}, False)
    assert st['revising']
    write(draft, 'Second version', 2)
    drafts.tick()
    assert st['status'] == 'editing'
    assert 'Update the post' in json.dumps(fresh_bot.messages[-1]['blocks'])

    uploads = len(fresh_bot.uploads)
    press('draft_post')
    assert len(fresh_bot.uploads) == uploads
    edit = next(u for u in fresh_bot.updates if u.get('ts') == POSTED_TS)
    assert edit['text'] == 'Second version'
    assert st['status'] == 'posted'


def test_keeping_the_post_changes_nothing(draft, fresh_bot):
    write(draft, 'First', 1)
    drafts.tick()
    press('draft_post')
    st = state.state['drafts'][KEY]
    st['revising'] = True
    write(draft, 'Second', 2)
    drafts.tick()
    press('draft_discard')
    assert st['status'] == 'posted'
    assert not any(u.get('ts') == POSTED_TS for u in fresh_bot.updates)


def test_a_post_from_before_is_found_in_the_channel(draft, fresh_bot):
    write(draft, 'First', 1)
    drafts.tick()
    st = state.state['drafts'][KEY]
    st.update(status='posted', revising=True)  # no 'posted' location stored
    write(draft, 'Fixed', 2)
    drafts.tick()
    press('draft_post')
    assert st['posted']['ts'] == POSTED_TS
    assert any(u.get('ts') == POSTED_TS and u['text'] == 'Fixed' for u in fresh_bot.updates)


def test_a_discarded_draft_says_so(draft, fresh_bot):
    write(draft, 'First', 1)
    drafts.tick()
    press('draft_discard')
    st = state.state['drafts'][KEY]
    routing.route({'channel': st['dm'], 'ts': '21.0', 'thread_ts': st['thread'], 'user': OWNER, 'text': 'x'}, False)
    assert 'discarded' in slack.app.client.text()
    assert not st.get('revising')
