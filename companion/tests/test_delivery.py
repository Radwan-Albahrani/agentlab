import json
import os

from bot import outbox, prompts, slack, state


def task_in(channel='C_TECH', thread='300.1', **extra):
    t = state.new_task(channel, thread, 'T1', 'logo', f'{channel}-{thread}', thread, None, **extra)
    os.makedirs(os.path.join(outbox.OUTBOX, t['outbox']), exist_ok=True)
    return t


def drop(t, name, data):
    with open(os.path.join(outbox.OUTBOX, t['outbox'], name), 'w') as f:
        json.dump(data, f)


def test_files_go_into_the_tasks_own_thread(fresh_bot):
    t = task_in()
    with open(os.path.join(outbox.OUTBOX, t['outbox'], 'proof.png'), 'wb') as f:
        f.write(b'png')
    drop(t, 'manifest.json', {'what': 'Proof', 'files': ['proof.png', 'notes.txt']})
    outbox.tick(t)
    assert [(u['channel'], u['thread_ts']) for u in fresh_bot.uploads] == [('C_TECH', '300.1')]
    assert not any(m['channel'] == 'D_OWNER' for m in fresh_bot.messages)


def test_a_post_to_its_own_channel_is_a_thread_reply(fresh_bot):
    t = task_in()
    drop(t, 'post.json', {'channel': 'C_TECH', 'text': 'Done, the logo is bigger.'})
    outbox.tick(t)
    sent = [m for m in fresh_bot.messages if m.get('text', '').startswith('Done')]
    assert sent and sent[0]['thread_ts'] == '300.1'


def test_a_new_channel_message_only_when_asked_for(fresh_bot):
    t = task_in()
    drop(t, 'post.json', {'channel': 'C_TECH', 'text': 'Release today!', 'new_message': True})
    outbox.tick(t)
    sent = [m for m in fresh_bot.messages if m.get('text', '').startswith('Release')]
    assert sent and sent[0].get('thread_ts') is None


def test_a_guests_approval_goes_to_the_owners_dm(fresh_bot):
    t = task_in(guest='U_SALAH')
    drop(t, 'approval.json', {'action': 'Change the live logo setting', 'details': 'x'})
    outbox.tick(t)
    ask = next(m for m in fresh_bot.messages if m['text'].startswith('Approve?'))
    assert ask['channel'] == 'D_OWNER'
    assert ['errand_approve', 'errand_reject'] in fresh_bot.actions()
    waiting = [m for m in fresh_bot.messages if m['channel'] == 'C_TECH' and 'Waiting for' in json.dumps(m)]
    assert waiting and waiting[0]['thread_ts'] == '300.1'


def test_a_guests_post_elsewhere_is_previewed_in_the_owners_dm(fresh_bot):
    t = task_in(guest='U_SALAH')
    drop(t, 'post.json', {'channel': 'C_RANDOM', 'text': 'Logo is bigger now'})
    outbox.tick(t)
    preview = next(m for m in fresh_bot.messages if m['text'] == 'Post this?')
    assert preview['channel'] == 'D_OWNER'
    assert not any(m.get('text', '').startswith('Logo') for m in fresh_bot.messages)


def test_a_guests_task_says_who_asked_and_what_needs_approval():
    p = prompts.task('make it bigger', 'Radwan', 'Slack channel C1', [], [], 'f', 'C1', [], '', 'Salah')
    assert 'Salah asked in' in p and "Radwan's explicit approval" in p and 'approval.json' in p
    assert 'Salah' not in prompts.task('x', 'Radwan', 'Slack channel C1', [], [], 'f', 'C1', [], '')


def test_a_new_message_gets_only_recent_context_and_is_not_called_a_thread(monkeypatch, fresh_bot):
    seen = {}

    def history(**kw):
        seen.update(kw)
        return {'messages': [{'ts': '1000.0', 'text': 'hello'}]}

    monkeypatch.setattr(fresh_bot, 'conversations_history', history)
    assert slack.thread_messages('C1', '1000.0', '1000.0') == [{'ts': '1000.0', 'text': 'hello'}]
    assert float(seen['oldest']) == 1000.0 - 15 * 60
    p = prompts.task('hello', 'Radwan', 'Slack channel C1', ['hello'], [], 'f', 'C1', [], '', 'Salah', True)
    assert 'new message' in p and 'whole thread' not in p
    assert 'whole thread' in prompts.task('x', 'Radwan', 'Slack channel C1', [], [], 'f', 'C1', [], '')
