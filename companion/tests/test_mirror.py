"""The case thread's copy of a colleague's thread (bot/mirror.py): every message, anyone's, exactly as it is there,
with who wrote it, where and when; edits and deletions follow; each copy in an explicit state."""

import json

import pytest
from bot import machine, mirror, routing, slack, state, t3, tasks
from conftest import agent_sends, set_settings

SALAH_DM = 'D_U_SALAH'


@pytest.fixture
def case(monkeypatch, t3_quiet, fresh_bot, tmp_path):
    """Salah messaged the bot in his DM: his task, with its case head in the owner's DM."""
    monkeypatch.setattr(t3, 'triage', lambda prompt: {'ok': True, 'result': 'It is checking.'})
    monkeypatch.setattr(tasks, 'history_with', lambda uid, now=None: [])

    def fetch(f, folder):
        if f['name'] == 'broken.pdf':
            return '', "couldn't download it: 403"
        p = tmp_path / f['name']
        p.write_bytes(b'x')
        return str(p), ''

    monkeypatch.setattr(slack, 'fetch', fetch)
    monkeypatch.setattr(slack, 'WORKSPACE', 'https://x.slack.com/')
    set_settings({'access': ['U_SALAH', 'U_ALI']})
    first = {'ts': '60.1', 'user': 'U_SALAH', 'text': 'Hi, how many trees offset 1 MW?'}
    fresh_bot.threads[(SALAH_DM, '60.1')] = [first]
    monkeypatch.setattr(slack, 'thread_messages', lambda ch, tts, trigger: [first])
    tasks.start(SALAH_DM, '60.1', '60.1', first['text'], guest='U_SALAH')
    return state.state['tasks'][state.key(SALAH_DM, '60.1')]


def copies(bot, t):
    """The copies in the case thread, in order: (head line, body JSON), uploads included."""
    out = []
    for m in bot.sent:
        if m.get('channel') != 'D_OWNER' or m.get('thread_ts') != t['case']['ts']:
            continue
        blocks = json.loads(m['blocks']) if isinstance(m.get('blocks'), str) else m.get('blocks') or []
        head = blocks[0]['elements'][-1]['text'] if blocks and blocks[0]['type'] == 'context' else ''
        if '  ·  ' in head:
            out.append((head, json.dumps(blocks[1:], ensure_ascii=False), m))
    return out


def say(bot, t, ts, user, text, files=None):
    routing.route(bot.say(SALAH_DM, '60.1', ts, user, text, files), '<@BCOMPANION>' in text)


def test_the_case_opens_with_a_copy_of_the_first_message_who_where_and_when(case, fresh_bot):
    (head, body, m), (line, progress, _) = copies(fresh_bot, case)
    assert line.startswith('*Companion*') and 'thinking' in progress  # its progress line there, copied too
    assert head.startswith('*Salah*  ·  <https://x.slack.com/archives/D_U_SALAH/p601|DM with Companion>  ·  <!date^60^')
    assert 'Hi, how many trees offset 1 MW?' in body
    assert m['blocks'][0]['elements'][0] == {
        'type': 'image',
        'image_url': 'https://img/U_SALAH.png',
        'alt_text': 'Salah',
    }
    assert case['mirror']['copies']['60.1']['state'] == 'copied'


def test_everything_said_in_the_thread_is_copied_in_order_files_too(case, fresh_bot):
    say(fresh_bot, case, '60.5', 'U_SALAH', 'fyi <@BCOMPANION>', [{'id': 'F9', 'name': 'TDF.xlsx', 'url_private': 'u'}])
    say(fresh_bot, case, '60.6', 'U_ALI', 'looks right to me')
    agent_sends(case, {'type': 'message', 'to': 'Salah', 'text': 'About 3,000 trees a year.'})
    heads = [(h.split('  ·  ')[0], b) for h, b, _ in copies(fresh_bot, case)]
    said = [(who, next(s for s in ('trees offset', 'fyi', 'looks right', '3,000') if s in b)) for who, b in heads
            if any(s in b for s in ('trees offset', 'fyi', 'looks right', '3,000'))]  # fmt: skip
    assert said == [('*Salah*', 'trees offset'), ('*Salah*', 'fyi'), ('*Ali*', 'looks right'),
                    ('*Companion*', '3,000')]  # fmt: skip
    (up,) = fresh_bot.uploads
    assert [f['filename'] for f in up['file_uploads']] == ['TDF.xlsx'] and 'fyi @BCOMPANION' in up['blocks']
    c = case['mirror']['copies']['60.5']
    assert c['copy'] == '1.5' and c['files'][0]['state'] == 'sent'  # where the upload landed, for edits


def test_a_mention_in_a_copy_is_plain_text_and_buttons_stay_behind(case, fresh_bot):
    rich = [{'type': 'rich_text', 'elements': [{'type': 'rich_text_section', 'elements': [
        {'type': 'user', 'user_id': 'U_OWNER'}, {'type': 'text', 'text': ' look'}]}]},
        {'type': 'actions', 'elements': [{'type': 'button', 'action_id': 'x'}]}]  # fmt: skip
    fresh_bot.threads[(SALAH_DM, '60.1')].append({'ts': '60.7', 'user': 'U_SALAH', 'text': '<@U_OWNER> look',
                                                  'blocks': rich})  # fmt: skip
    mirror.sync(case)
    _, body, _ = copies(fresh_bot, case)[-1]
    assert '"text": "@Sam"' in body and 'U_OWNER' not in body and 'button' not in body


def test_an_edit_updates_the_copy_and_a_deletion_says_so(case, fresh_bot):
    say(fresh_bot, case, '60.5', 'U_SALAH', 'its 1 MW')
    copy_ts = case['mirror']['copies']['60.5']['copy']
    msg = next(m for m in fresh_bot.threads[(SALAH_DM, '60.1')] if m['ts'] == '60.5')
    msg.update(text='its 2 MW', edited={'user': 'U_SALAH', 'ts': '61.0'})
    routing.route({'channel': SALAH_DM, 'subtype': 'message_changed', 'message': dict(msg)}, False)
    edit = [u for u in fresh_bot.updates if u['ts'] == copy_ts][-1]
    assert edit['ts'] == copy_ts and 'its 2 MW' in json.dumps(edit) and '_edited_' in json.dumps(edit)
    assert case['mirror']['copies']['60.5']['state'] == 'edited'
    fresh_bot.threads[(SALAH_DM, '60.1')].remove(msg)
    routing.route({'channel': SALAH_DM, 'subtype': 'message_deleted', 'deleted_ts': '60.5',
                   'previous_message': dict(msg)}, False)  # fmt: skip
    gone = [u for u in fresh_bot.updates if u['ts'] == copy_ts][-1]
    assert gone['ts'] == copy_ts and 'Salah* deleted this message' in json.dumps(gone)
    assert case['mirror']['copies']['60.5']['state'] == 'deleted'


def test_syncing_again_changes_nothing(case, fresh_bot):
    say(fresh_bot, case, '60.5', 'U_SALAH', 'hello')
    n, u = len(fresh_bot.messages), len(fresh_bot.updates)
    mirror.sync(case)
    mirror.sweep()
    assert (len(fresh_bot.messages), len(fresh_bot.updates)) == (n, u)


def test_a_copy_slack_refuses_is_retried_and_the_order_kept(case, fresh_bot, monkeypatch):
    post = fresh_bot.chat_postMessage

    def down(**kw):
        if kw['channel'] == 'D_OWNER':
            raise RuntimeError('ratelimited')
        return post(**kw)

    monkeypatch.setattr(fresh_bot, 'chat_postMessage', down)
    fresh_bot.say(SALAH_DM, '60.1', '60.5', 'U_SALAH', 'one')
    fresh_bot.say(SALAH_DM, '60.1', '60.6', 'U_SALAH', 'two')
    mirror.sync(case)
    copies_now = case['mirror']['copies']
    assert copies_now['60.5']['state'] == 'failed' and '60.6' not in copies_now  # two waits for one
    monkeypatch.setattr(fresh_bot, 'chat_postMessage', post)
    mirror.sync(case)
    bodies = [b for _, b, _ in copies(fresh_bot, case)]
    assert 'one' in bodies[-2] and 'two' in bodies[-1]
    assert copies_now['60.5']['state'] == 'copied' and copies_now['60.6']['state'] == 'copied'


def test_a_file_that_cannot_be_passed_on_is_named_with_why(case, fresh_bot):
    say(fresh_bot, case, '60.5', 'U_SALAH', 'see this', [{'id': 'F8', 'name': 'broken.pdf'}])
    body = next(b for _, b, _ in copies(fresh_bot, case) if 'see this' in b)
    assert not fresh_bot.uploads and 'see this' in body and "broken.pdf held (couldn't download it: 403)" in body


def test_a_case_from_before_the_mirror_copies_only_what_comes_next(case, fresh_bot):
    del case['mirror']
    fresh_bot.say(SALAH_DM, '60.1', '60.5', 'U_SALAH', 'old news')
    mirror.sync(case)
    say(fresh_bot, case, '60.6', 'U_SALAH', 'new news')
    bodies = [b for _, b, _ in copies(fresh_bot, case)]
    assert not any('old news' in b for b in bodies) and any('new news' in b for b in bodies)


def test_an_errand_or_a_task_without_a_case_is_not_mirrored(case):
    assert mirror.follows(case)
    errand = dict(case, case={'ch': 'D_OWNER', 'ts': '9.0', 'head': 'errand', 'mode': 'private'})
    assert not mirror.follows(errand) and not mirror.follows({**case, 'case': None})
    assert machine.is_colleague(case)


def test_an_upload_slack_wont_take_blocks_for_carries_the_copy_as_a_comment(case, fresh_bot, monkeypatch):
    upload = fresh_bot.files_upload_v2

    def no_blocks(**kw):
        if 'blocks' in kw:
            raise RuntimeError('invalid_blocks')
        return upload(**kw)

    monkeypatch.setattr(fresh_bot, 'files_upload_v2', no_blocks)
    say(fresh_bot, case, '60.5', 'U_SALAH', 'the sheet', [{'id': 'F9', 'name': 'TDF.xlsx', 'url_private': 'u'}])
    (up,) = fresh_bot.uploads
    assert up['initial_comment'].startswith('*Salah*  ·  ') and up['initial_comment'].endswith('the sheet')
    assert case['mirror']['copies']['60.5']['files'][0]['state'] == 'sent'


def test_a_link_preview_slack_adds_later_is_not_an_edit(case, fresh_bot):
    say(fresh_bot, case, '60.5', 'U_SALAH', 'see https://example.com')
    msg = next(m for m in fresh_bot.threads[(SALAH_DM, '60.1')] if m['ts'] == '60.5')
    msg['attachments'] = [{'from_url': 'https://example.com', 'text': 'Example Domain'}]
    n = len(fresh_bot.updates)
    mirror.sync(case)
    assert len(fresh_bot.updates) == n and case['mirror']['copies']['60.5']['state'] == 'copied'
