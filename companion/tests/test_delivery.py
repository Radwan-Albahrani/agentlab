import json
import os

import pytest
from bot import attachments, ledger, machine, outbox, posts, prompts, slack, state
from conftest import ROUTE, agent_sends, click, receipts


def task_in(channel='C_TECH', thread='300.1', guest=None):
    t = state.new_task(
        channel, thread, 'T1', 'logo', f'{channel}-{thread}', thread, None, ROUTE, party=machine.party_of(guest)
    )
    if guest:
        machine.open_case(t, 'D_OWNER', '900.1', 'own')
    machine.begin_turn(t, 'colleague' if guest else 'owner', 'thread')
    os.makedirs(os.path.join(outbox.OUTBOX, t['outbox']), exist_ok=True)
    return t


def test_files_go_into_the_tasks_own_thread(fresh_bot):
    t = task_in()
    with open(os.path.join(outbox.OUTBOX, t['outbox'], 'proof.png'), 'wb') as f:
        f.write(b'png')
    agent_sends(t, {'type': 'message', 'to': 'thread', 'text': 'Proof', 'files': ['proof.png', 'notes.txt']})
    assert [(u['channel'], u['thread_ts']) for u in fresh_bot.uploads] == [('C_TECH', '300.1')]
    assert not any(m['channel'] == 'D_OWNER' for m in fresh_bot.messages)
    (it,) = ledger.items(t)
    assert it['state'] == 'sent' and states(it) == [('proof.png', 'sent', ''), ('notes.txt', 'held', 'missing')]


def states(it):
    return [(a['name'], a['state'], a['note']) for a in it['attachments']]


def put(t, *names):
    for n in names:
        with open(os.path.join(outbox.OUTBOX, t['outbox'], n), 'wb') as f:
            f.write(b'x')


def test_files_for_someone_by_dm_go_with_the_message_once_the_owner_sends_it(fresh_bot):
    t = task_in()
    put(t, 'TDF-trees.xlsx', 'claims.zip', 'run.sh')
    files = ['TDF-trees.xlsx', 'claims.zip', 'run.sh']
    box = agent_sends(t, {'type': 'message', 'to': 'Ali', 'text': 'The tree sheet.', 'files': files})
    card = fresh_bot.text()
    assert '_With 2 files: TDF-trees.xlsx, claims.zip_' in card and 'Held back: run.sh (file type not allowed)' in card
    assert not fresh_bot.uploads  # nothing leaves before the owner says so
    click(fresh_bot, 'post_send')
    (up,) = fresh_bot.uploads
    assert up['channel'] == 'D_U_ALI' and [f['filename'] for f in up['file_uploads']] == [
        'TDF-trees.xlsx',
        'claims.zip',
    ]
    sent = (
        'Message sent to Ali by DM · files: TDF-trees.xlsx sent · claims.zip sent · run.sh held (file type not allowed)'
    )
    assert ledger.items(t)[-1]['note'] == sent
    (r,) = receipts(box)
    assert r['state'] == 'sent' and r['files'] == [
        {'name': 'TDF-trees.xlsx', 'state': 'sent', 'why': ''},
        {'name': 'claims.zip', 'state': 'sent', 'why': ''},
        {'name': 'run.sh', 'state': 'held', 'why': 'file type not allowed'},
    ]


def test_files_alone_need_no_text_and_a_poll_cannot_carry_them(fresh_bot):
    t = task_in()
    put(t, 'chart.png')
    agent_sends(t, {'type': 'message', 'to': '#ask-tech', 'files': ['chart.png']})
    assert [u['channel'] for u in fresh_bot.uploads] == ['C_TECH'] and ledger.items(t)[-1]['state'] == 'sent'
    poll = {'question': 'Ship?', 'options': ['Yes', 'No'], 'closes': '2099-01-01T00:00:00+00:00'}
    agent_sends(t, {'type': 'message', 'to': '#ask-tech', 'text': 'Vote', 'poll': poll, 'files': ['chart.png']})
    it = ledger.items(t)[-1]
    assert "a poll can't carry files" in it['note'] and states(it) == [('chart.png', 'withheld', 'refused')]


def test_files_of_a_message_the_owner_turns_down_are_withheld(fresh_bot):
    t = task_in()
    put(t, 'a.pdf')
    agent_sends(t, {'type': 'message', 'to': 'Ali', 'text': 'Here', 'files': ['a.pdf']})
    click(fresh_bot, 'post_skip')
    assert states(ledger.items(t)[-1]) == [('a.pdf', 'withheld', 'rejected by the owner')] and not fresh_bot.uploads


def test_a_failed_upload_marks_its_files_failed_and_the_message_still_sent(fresh_bot, monkeypatch):
    t = task_in(guest='U_SALAH')
    put(t, 'a.pdf')

    def refuse(**kw):
        raise RuntimeError('file_upload_failed')

    monkeypatch.setattr(fresh_bot, 'files_upload_v2', refuse)
    agent_sends(t, {'type': 'message', 'to': 'colleague', 'text': 'Here', 'files': ['a.pdf']})
    it = ledger.items(t)[-1]
    assert it['state'] == 'sent' and states(it) == [('a.pdf', 'failed', "Slack didn't take it: file_upload_failed")]
    assert "went without a.pdf (failed: Slack didn't take it" in fresh_bot.text()  # the owner's case says so


def test_a_message_cannot_be_recorded_sent_while_its_files_wait():
    t = task_in()
    put(t, 'a.pdf')
    it = ledger.add(t, 'message', to='people', label='Ali', text='x', files=['a.pdf'])
    attachments.check(it, os.path.join(outbox.OUTBOX, t['outbox']))
    with pytest.raises(ledger.IllegalMoveError, match='still waiting to go'):
        ledger.move(t, it, 'sent')


def test_the_agent_is_told_how_to_send_files_to_anyone():
    rules = prompts.sending('/box', 'Sam', [])
    assert 'any message can carry them, whoever it is to' in rules and 'xlsx' in rules and '50 MB' in rules


def test_a_message_to_its_own_channel_is_a_new_message_there_at_once(fresh_bot):
    t = task_in()
    agent_sends(t, {'type': 'message', 'to': '#ask-tech', 'text': 'Release today!'})
    sent = [m for m in fresh_bot.messages if m.get('text', '').startswith('Release')]
    assert sent and sent[0]['channel'] == 'C_TECH' and sent[0].get('thread_ts') is None
    assert 'post_send' not in json.dumps(fresh_bot.actions())


def test_a_colleagues_approval_goes_to_the_case_and_nothing_to_them(fresh_bot):
    t = task_in(guest='U_SALAH')
    agent_sends(t, {'type': 'approval', 'action': 'Change the live logo setting', 'details': 'x'})
    ask = next(m for m in fresh_bot.messages if m['text'].startswith('Approve?'))
    assert (ask['channel'], ask['thread_ts']) == ('D_OWNER', '900.1')
    assert ['errand_approve', 'errand_reject'] in fresh_bot.actions()
    assert not any(m['channel'] == 'C_TECH' for m in fresh_bot.messages)  # the agent tells them, if it chooses
    assert t['phase'] == 'waiting_owner'


def test_a_colleagues_post_elsewhere_is_previewed_in_the_case(fresh_bot):
    t = task_in(guest='U_SALAH')
    agent_sends(t, {'type': 'message', 'to': '#random', 'text': 'Logo is bigger now'})
    preview = next(m for m in fresh_bot.messages if m['text'] == 'Post this?')
    assert (preview['channel'], preview['thread_ts']) == ('D_OWNER', '900.1')
    assert not any(m.get('text', '').startswith('Logo') for m in fresh_bot.messages)


def test_in_a_colleagues_case_thread_means_nothing_name_them(fresh_bot):
    t = task_in(guest='U_SALAH')
    agent_sends(t, {'type': 'message', 'to': 'thread', 'text': 'x'})
    (it,) = ledger.items(t)
    assert it['state'] == 'refused' and 'write their name as "to"' in it['note']


def test_a_colleagues_task_says_who_hears_what_and_what_needs_approval():
    p = prompts.task('make it bigger', 'Radwan', 'Slack channel C1', [], [], 'f', 'C1', [], '', 'Salah')
    assert 'Salah asked in' in p and "Needs Radwan's OK first" in p and '"type": "approval"' in p
    assert 'Salah** hears only the messages you send them ("to": "Salah")' in p
    assert 'Radwan** gets your final message' in p and 'receipts.json' in p
    assert 'work accounts' not in p and 'poll' not in p  # neither is theirs to use
    assert 'Salah' not in prompts.task('x', 'Radwan', 'Slack channel C1', [], [], 'f', 'C1', [], '')
    assert 'approved this request' not in p


def test_an_approved_ask_checks_back_when_a_follow_up_leaves_it_or_wants_sensitive_data():
    p = prompts.task('make it bigger', 'Radwan', 'Slack channel C1', [], [], 'f', 'C1', [], '', 'Salah', approved=True)
    assert 'Radwan approved this request as Salah asked it above, and only that' in p
    assert 'clearly bigger job' in p and 'sensitive or confidential information' in p and '"approval"' in p


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


def test_a_sent_message_can_be_edited_after_a_preview(fresh_bot):
    t = task_in(channel='D_OWNER', thread='301.1')
    agent_sends(t, {'type': 'message', 'to': '#ask-tech', 'text': "Post-mortem for last night's outage"})
    click(fresh_bot, 'post_send')
    (sent,) = ledger.items(t)
    assert sent['state'] == 'sent' and sent['where'] == 'in #general'  # the fake Slack names every channel so
    posted = sent['msgs'][0]
    assert f'- {sent["id"]}: in #general:' in prompts.editing('Sam', posts.sent_list(t))
    agent_sends(t, {'type': 'edit', 'id': sent['id'], 'text': "Post-mortem for today's outage"})
    assert fresh_bot.messages[-1]['text'] == 'Edit this?' and 'Edit it' in json.dumps(fresh_bot.messages[-1])
    click(fresh_bot, 'post_send')
    edited = next(u for u in fresh_bot.updates if u['channel'] == 'C_TECH')
    assert (edited['channel'], edited['ts']) == posted and "today's outage" in json.dumps(edited)
    assert sent['text'] == "Post-mortem for today's outage" and ledger.items(t)[-1]['state'] == 'sent'


def test_an_edit_of_a_message_it_never_sent_is_refused(fresh_bot):
    t = task_in()
    agent_sends(t, {'type': 'edit', 'id': '3', 'text': 'x'})
    (it,) = ledger.items(t)
    assert it['state'] == 'refused' and 'names no message this task sent' in it['note']
    assert 'names no message this task sent' in fresh_bot.text() and not fresh_bot.updates
