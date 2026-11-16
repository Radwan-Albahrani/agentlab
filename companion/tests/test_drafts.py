import json
import os
import shutil
import time

import pytest
from bot import drafts, prompts, routing, slack, state, t3
from conftest import OWNER

KEY = '2026-11-01'
POSTED_TS = f'{time.time() + 50:.6f}'  # after the uploads below, before any ready.json is stamped


@pytest.fixture
def draft(fresh_bot, monkeypatch):
    d = os.path.join(drafts.DRAFTS, KEY)
    os.makedirs(d, exist_ok=True)
    monkeypatch.setattr(drafts.time, 'sleep', lambda s: None)
    monkeypatch.setattr(t3, 'start_thread', lambda project, title, message: ('T_REV', ''))
    monkeypatch.setattr(drafts, '_refused', {})
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


def write_files(d, names, meta=None):
    with open(os.path.join(d, 'update.md'), 'w', encoding='utf-8') as f:
        f.write('This week')
    for n in names:
        with open(os.path.join(d, n), 'wb') as f:
            f.write(b'x' * 10)
    ready = os.path.join(d, 'ready.json')
    with open(ready, 'w') as f:
        json.dump({'title': 'Weekly', 'revision': 1, **(meta or {})}, f)
    stamp = time.time() + 101
    os.utime(ready, (stamp, stamp))


def uploaded(upload):
    return [u['filename'] for u in upload['file_uploads']]


def test_without_ready_json_images_a_video_is_picked_up_and_goes_first(draft, fresh_bot):
    write_files(draft, ['1-wall.png', 'update.mp4', '2-dir.png'])
    drafts.tick()
    assert uploaded(fresh_bot.uploads[-1]) == ['update.mp4', '1-wall.png', '2-dir.png']
    assert 'screenshots or video' not in json.dumps(fresh_bot.messages[-1]['blocks'])  # only said while editing


def test_ready_json_images_are_uploaded_exactly_as_listed(draft, fresh_bot):
    write_files(draft, ['shot.png', 'demo.mp4', 'extra.png'], {'images': ['shot.png', 'demo.mp4']})
    drafts.tick()
    assert uploaded(fresh_bot.uploads[-1]) == ['shot.png', 'demo.mp4']


def test_screenshots_alone_upload_as_before(draft, fresh_bot, monkeypatch):
    def no_info(**kw):
        raise AssertionError('files.info is only for video posts')

    fresh_bot.files_info = no_info
    write(draft, 'Only shots', 1)
    drafts.tick()
    press('draft_post')
    st = state.state['drafts'][KEY]
    assert uploaded(fresh_bot.uploads[-1]) == ['shot.png']
    assert st['posted']['ts'] == POSTED_TS  # found by the history scan, as before
    assert not hasattr(fresh_bot, 'timeout')


def video_post(draft, fresh_bot, shares_after):
    """Post a video draft; files.info shows the channel share after `shares_after` calls (None: never)."""
    calls = []
    fresh_bot.files_upload_v2 = lambda **kw: fresh_bot.uploads.append(kw) or {'files': [{'id': 'F9'}]}

    def files_info(file):
        calls.append(file)
        ready = shares_after is not None and len(calls) > shares_after
        channel = fresh_bot.uploads[-1]['channel']
        return {'file': {'shares': {'public': {channel: [{'ts': '777.000100'}]}} if ready else {}}}

    fresh_bot.files_info = files_info
    write_files(draft, ['update.mp4'])
    drafts.tick()
    press('draft_post')
    return state.state['drafts'][KEY], calls


def test_a_video_post_finds_its_message_through_files_info(draft, fresh_bot):
    st, calls = video_post(draft, fresh_bot, shares_after=3)
    assert st['status'] == 'posted' and st['posted']['ts'] == '777.000100'
    assert calls == ['F9'] * 4


def test_a_video_post_falls_back_to_the_history_scan_after_the_timeout(draft, fresh_bot):
    st, calls = video_post(draft, fresh_bot, shares_after=None)
    assert len(calls) == drafts.SHARE_TRIES
    assert st['posted']['ts'] == POSTED_TS


def test_a_video_upload_uses_a_long_timeout_client(draft, fresh_bot, monkeypatch):
    seen = []
    monkeypatch.setattr(drafts, '_uploader', lambda: seen.append(1) or fresh_bot)
    write_files(draft, ['update.mp4'])
    drafts.tick()
    assert seen and fresh_bot.uploads


def test_a_file_over_the_cap_is_reported_once_and_not_uploaded(draft, fresh_bot, monkeypatch):
    monkeypatch.setattr(drafts, 'MAX_MB', 0.000001)
    write_files(draft, ['update.mp4'])
    drafts.tick()
    drafts.tick()
    assert not fresh_bot.uploads
    refused = [m for m in fresh_bot.messages if "can't be previewed" in json.dumps(m)]
    assert len(refused) == 1 and 'update.mp4' in json.dumps(refused[0])
    assert KEY not in state.state['drafts']


def test_the_revision_brief_mentions_video_only_when_the_draft_has_one():
    plain = prompts.revise_draft('/f', KEY, 'Sam', 'shorter', 2)
    assert 'the screenshots listed in' in plain and 'video' not in plain
    video = prompts.revise_draft('/f', KEY, 'Sam', 'shorter', 2, video=True)
    assert 'attachments (screenshots or video)' in video and 'never reference them inside update.md' in video
