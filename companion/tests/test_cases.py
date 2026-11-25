"""Cases: a colleague's conversation with the companion, followed by the owner from a thread in their DM. Every
message in and out is a ledger item with an explicit state; party, case, turn and phase are explicit too."""

import json
import os

import pytest
from bot import jobs, ledger, machine, routing, slack, state, t3, tasks
from conftest import OWNER, ROUTE, agent_sends, click, receipts, set_settings

SALAH_DM = 'D_U_SALAH'  # Salah's DM with the bot


def snapshot(status, answer, **more):
    return lambda tid, since: {
        'running': False,
        'last_status': status,
        'last_done': state.now_iso(),
        'messages': [('m1', state.now_iso(), answer)],
        'requests': [],
        'workers': [],
        'prs': [],
        **more,
    }


@pytest.fixture
def case(monkeypatch, t3_quiet, fresh_bot):
    """Salah messaged the bot in his DM: his task, with its case head in the owner's DM."""
    sent = []
    monkeypatch.setattr(t3, 'send', lambda tid, msg: sent.append(msg) or {'ok': True})
    monkeypatch.setattr(t3, 'triage', lambda prompt: {'ok': True, 'result': 'It is checking the stack.'})
    monkeypatch.setattr(t3, 'digest', lambda tid: 'record')
    monkeypatch.setattr(jobs, 'run_later', lambda fn, *a: fn(*a))
    monkeypatch.setattr(tasks, 'history_with', lambda uid, now=None: [])
    message = {'ts': '60.1', 'user': 'U_SALAH', 'text': 'I fixed them'}
    monkeypatch.setattr(slack, 'thread_messages', lambda ch, tts, trigger: [message])
    tasks.start(SALAH_DM, '60.1', '60.1', 'I fixed them', guest='U_SALAH')
    t = state.state['tasks'][state.key(SALAH_DM, '60.1')]
    return t, sent


def posted(bot, ch, thread=None):
    return [m for m in bot.messages if m['channel'] == ch and (thread is None or m.get('thread_ts') == thread)]


def text_of(msgs):
    return json.dumps(msgs, ensure_ascii=False)


def in_case(bot, t):
    return text_of(posted(bot, 'D_OWNER', t['case']['ts']))


def kinds(t):
    return [(i['kind'], i.get('to', ''), i['state']) for i in ledger.items(t)]


def finish(t, monkeypatch, answer, status='completed', **more):
    monkeypatch.setattr(t3, 'snapshot', snapshot(status, answer, **more))
    tasks.tick(t)


def test_a_colleagues_message_opens_a_case_with_every_state_named(case, fresh_bot):
    t, _ = case
    assert t['party'] == {'kind': 'colleague', 'user': 'U_SALAH'}
    assert t['case']['head'] == 'own' and t['case']['mode'] == 'private' and t['case']['ch'] == 'D_OWNER'
    assert t['turn']['by'] == 'colleague' and t['turn']['state'] == 'running' and t['phase'] == 'working'
    assert kinds(t) == [('in', '', 'received')]
    head = next(m for m in fresh_bot.messages if m.get('thread_ts') is None and m['channel'] == 'D_OWNER')
    assert 'Salah' in text_of(head) and 'I fixed them' in text_of(head)
    assert not any(k in t for k in ('guest', 'active', 'outcome', 'answer_to'))


def test_the_colleague_hears_only_what_the_agent_sends_and_its_final_message_is_the_owners(
    case, fresh_bot, monkeypatch
):
    t, _ = case
    agent_sends(t, {'type': 'message', 'to': 'Salah', 'text': 'All 16 PRs check out.'})
    finish(t, monkeypatch, 'Told Salah the stack is fine; #6257 still needs a test.')
    theirs = text_of(posted(fresh_bot, SALAH_DM, '60.1'))
    assert 'All 16 PRs' in theirs and 'needs a test' not in theirs
    case_thread = in_case(fresh_bot, t)
    assert 'Companion → Salah' in case_thread and 'All 16 PRs' in case_thread  # what went, copied
    assert 'Companion → you' in case_thread and 'needs a test' in case_thread  # the agent's word to the owner
    assert 'Nothing was sent' not in case_thread
    assert kinds(t) == [('in', '', 'received'), ('message', 'colleague', 'sent'), ('final', 'case', 'sent')]
    assert t['turn'] | {'at': 0, 'ended': 0} == {
        'n': 1, 'by': 'colleague', 'place': 'thread', 'state': 'ended', 'outcome': 'answered', 'at': 0, 'ended': 0
    }  # fmt: skip
    assert t['phase'] == 'answered'


def test_a_turn_that_sent_the_colleague_nothing_says_so_in_the_case(case, fresh_bot, monkeypatch):
    t, _ = case
    finish(t, monkeypatch, 'Salah wants the logs; asking you first.')
    assert 'asking you first' not in text_of(posted(fresh_bot, SALAH_DM, '60.1'))
    assert 'Nothing was sent to Salah this turn' in in_case(fresh_bot, t)


def test_a_message_for_anyone_else_waits_for_the_owners_preview(case, fresh_bot):
    t, _ = case
    agent_sends(
        t,
        {'type': 'message', 'to': 'Salah', 'text': 'On it.'},
        {'type': 'message', 'to': '#random', 'text': 'Release today!'},
    )
    assert 'On it.' in text_of(posted(fresh_bot, SALAH_DM, '60.1'))
    preview = next(m for m in fresh_bot.messages if m['text'] == 'Post this?')
    assert (preview['channel'], preview['thread_ts']) == ('D_OWNER', t['case']['ts'])
    assert not any(m['channel'] == 'C_RANDOM' for m in fresh_bot.messages)
    assert t['phase'] == 'waiting_owner'
    click(fresh_bot, 'post_skip')
    assert t['phase'] == 'working' and ledger.items(t)[-1]['state'] == 'rejected'


def test_the_owner_talks_to_the_agent_privately_in_the_case(case, fresh_bot, monkeypatch):
    t, sent = case
    finish(t, monkeypatch, 'Done.')
    before = len(posted(fresh_bot, SALAH_DM))
    routing.route(
        {
            'channel': 'D_OWNER',
            'channel_type': 'im',
            'ts': '90.1',
            'thread_ts': t['case']['ts'],
            'user': OWNER,
            'text': 'is the engine real?',
        },
        False,
    )
    assert 'is the engine real?' in sent[-1] and 'sees none of this' in sent[-1]
    assert t['turn']['by'] == 'owner' and t['turn']['n'] == 2
    last = ledger.items(t)[-1]
    assert (last['kind'], last['private'], last['by']) == ('in', True, OWNER)
    finish(t, monkeypatch, 'No: the engine repo does not exist.')
    assert 'engine repo' in in_case(fresh_bot, t)
    assert len(posted(fresh_bot, SALAH_DM)) == before  # nothing reached Salah, not even a thinking line


def test_on_the_owners_word_the_agent_sends_the_colleague_a_message(case, fresh_bot):
    t, _ = case
    box = agent_sends(
        t, {'type': 'message', 'to': 'Salah', 'text': 'The stack is on hold until the engine is in a repo.'}
    )
    assert 'on hold' in text_of(posted(fresh_bot, SALAH_DM, '60.1'))
    assert 'Companion → Salah' in in_case(fresh_bot, t)
    assert not os.path.exists(os.path.join(box, 'send.json'))
    (r,) = receipts(box)
    assert r == {
        'id': '2', 'type': 'message', 'to': 'Salah', 'state': 'sent', 'meaning': 'sent', 'note': '',
        'text': 'The stack is on hold until the engine is in a repo.', 'files': [],
    }  # fmt: skip


def test_a_colleague_writing_while_the_owner_talks_waits_its_turn(case, fresh_bot, monkeypatch):
    t, sent = case
    finish(t, monkeypatch, 'Done.')
    routing.route(
        {'channel': 'D_OWNER', 'channel_type': 'im', 'ts': '91.1', 'thread_ts': t['case']['ts'], 'user': OWNER,
         'text': 'hold on'},
        False,
    )  # fmt: skip
    n = len(sent)
    tasks.follow_up(t, 'the staging log is attached now', None, '92.1', 'thread', 'U_SALAH')
    assert len(sent) == n and t['queue'][0]['text'] == 'the staging log is attached now'
    assert 'the staging log is attached now' in in_case(fresh_bot, t)  # the owner sees it at once
    finish(t, monkeypatch, 'Holding.')  # the owner's turn ends: Salah's message goes to the agent now, as his turn
    assert len(sent) == n + 1 and 'Salah' in sent[-1] and 'the staging log is attached now' in sent[-1]
    assert t['turn']['by'] == 'colleague' and t['turn']['state'] == 'running'


def test_a_turn_the_owner_starts_in_t3_answers_the_owner(case, fresh_bot, monkeypatch):
    t, _ = case
    finish(t, monkeypatch, 'Done.')
    monkeypatch.setattr(t3, 'has_open_run', lambda tid: True)
    monkeypatch.setattr(t3, 'snapshot', lambda tid, since: {**snapshot('completed', 'x')(tid, since), 'running': True})
    tasks.tick(t)
    assert t['turn']['by'] == 't3' and machine.owners_turn(t) and machine.final_goes_to(t) == 'case'


def test_approvals_go_in_the_case_and_a_newer_one_replaces_the_old(case, fresh_bot):
    t, _ = case
    agent_sends(t, {'type': 'approval', 'action': 'Merge the stack', 'details': 'x'})
    agent_sends(t, {'type': 'approval', 'action': 'Merge only #6257', 'details': 'y'})
    first, second = (i for i in ledger.items(t) if i['kind'] == 'approval')
    assert first['state'] == 'replaced' and second['state'] == 'awaiting_owner'
    assert first['card']['ch'] == 'D_OWNER' and 'Replaced by a newer request' in fresh_bot.text()
    click(fresh_bot, 'errand_approve', nth=0)  # the old card's button decides nothing
    assert second['state'] == 'awaiting_owner' and t['phase'] == 'waiting_owner'
    click(fresh_bot, 'errand_approve')
    assert second['state'] == 'approved' and t['turn']['by'] == 'decision'


def test_the_agent_can_withdraw_its_approval_request(case, fresh_bot):
    t, _ = case
    agent_sends(t, {'type': 'approval', 'action': 'Merge the stack', 'details': 'x'})
    agent_sends(t, {'type': 'withdraw', 'why': 'the engine is not in a repo yet'})
    (a,) = ledger.items(t)[1:]
    assert a['state'] == 'withdrawn' and 'Withdrawn by' in fresh_bot.text() and t['phase'] == 'working'
    click(fresh_bot, 'errand_approve')
    assert a['state'] == 'withdrawn'  # nothing left to approve


def test_the_agents_question_comes_to_the_owner_and_their_reply_answers_it(case, fresh_bot, monkeypatch):
    t, _ = case
    ask = {'questions': [{'question': 'Merge #6257 too?', 'options': [{'label': 'Yes'}, {'label': 'No'}]}]}
    running = snapshot('running', '', requests=[('r1', 'user_input', ask)])
    monkeypatch.setattr(t3, 'snapshot', lambda tid, since: {**running(tid, since), 'running': True})
    tasks.tick(t)
    assert 'Merge #6257 too?' in in_case(fresh_bot, t) and 'Merge #6257' not in text_of(posted(fresh_bot, SALAH_DM))
    assert t['phase'] == 'waiting_answer'
    monkeypatch.setattr(t3, 'waiting_question', lambda tid: True)
    answered = []
    monkeypatch.setattr(t3, 'answer', lambda tid, msg: answered.append(msg) or {'ok': True})
    routing.route(
        {'channel': 'D_OWNER', 'channel_type': 'im', 'ts': '93.1', 'thread_ts': t['case']['ts'], 'user': OWNER,
         'text': '1'},
        False,
    )  # fmt: skip
    assert answered and answered[-1].endswith('Yes') and 'queue' not in t


def test_a_colleague_talking_in_a_review_they_asked_for_opens_a_shared_case(monkeypatch, t3_quiet, fresh_bot):
    monkeypatch.setattr(t3, 'send', lambda tid, msg: {'ok': True})
    t = state.new_task(
        'C_TECH', '80.1', 'T_REV', 'Review #6257', 'rev-box', '80.1', None, ROUTE, party=machine.party_of()
    )
    t['audit'] = tasks.audit('U_SALAH', 'in #tech')
    machine.begin_turn(t, 'system', 'thread')
    machine.end_turn(t, 'answered')
    tasks.follow_up(t, 'why did it fail the migration check?', None, '81.1', 'thread', 'U_SALAH')
    assert t['party'] == {'kind': 'colleague', 'user': 'U_SALAH'} and t['case']['mode'] == 'shared'
    assert 'migration check' in in_case(fresh_bot, t)
    tasks.reply(t, 'The migration drops a column still read by the map.')
    assert 'drops a column' in text_of(posted(fresh_bot, 'C_TECH', '80.1'))  # answered where they asked
    assert 'drops a column' in in_case(fresh_bot, t)  # and copied


def test_the_owners_own_task_keeps_no_case(monkeypatch, t3_quiet, fresh_bot):
    monkeypatch.setattr(t3, 'send', lambda tid, msg: {'ok': True})
    t = state.new_task('C_TECH', '82.1', 'T_OWN', 'logo', 'own-box', '82.1', None, ROUTE, party=machine.party_of())
    t['audit'] = tasks.audit(OWNER, 'in #tech')
    machine.begin_turn(t, 'owner', 'thread')
    machine.end_turn(t, 'answered')
    tasks.follow_up(t, 'make it blue too', None, '83.1', 'thread', 'U_SALAH')
    assert 'case' not in t and t['party']['kind'] == 'owner'


def test_a_colleagues_side_question_goes_to_the_agent_and_never_gets_the_record(case, fresh_bot, monkeypatch):
    # what the agent is doing is its work for the owner: the colleague hears only what it chooses to send them
    t, sent = case
    finish(t, monkeypatch, 'Done.')
    n = len(sent)
    tasks.follow_up(t, '/btw what is it doing?', None, '94.1', 'thread', 'U_SALAH')
    assert len(sent) == n + 1 and 'what is it doing?' in sent[-1]
    assert 'It is checking the stack.' not in text_of(posted(fresh_bot, SALAH_DM))


def test_a_colleagues_queued_message_gets_a_plain_receipt(case, fresh_bot, monkeypatch):
    t, _ = case
    monkeypatch.setattr(t3, 'send', lambda tid, msg: {'ok': True, 'result': {'delivery': 'queued'}})
    tasks.follow_up(t, 'one more thing: the client is the ministry', None, '96.1', 'thread', 'U_SALAH')
    theirs = text_of(posted(fresh_bot, SALAH_DM))
    assert "Got it. I'll read this as soon as I finish the step I'm on." in theirs
    assert 'Right now' not in theirs and 'It is checking the stack.' not in theirs


def test_the_owners_side_questions_are_answered_on_the_side_and_start_no_turn(case, fresh_bot, monkeypatch):
    t, sent = case
    finish(t, monkeypatch, 'Done.')
    n, turn = len(sent), dict(t['turn'])
    routing.route(
        {'channel': 'D_OWNER', 'channel_type': 'im', 'ts': '95.1', 'thread_ts': t['case']['ts'], 'user': OWNER,
         'text': 'status?'},
        False,
    )  # fmt: skip
    assert len(sent) == n and t['turn'] == turn and ledger.items(t)[-1]['to'] == 'owner'
    assert 'It is checking the stack.' in in_case(fresh_bot, t)
    assert 'It is checking the stack.' not in text_of(posted(fresh_bot, SALAH_DM))


def test_moves_the_state_machine_does_not_allow_are_bugs_not_states(case):
    t, _ = case
    it = ledger.add(t, 'message', to='colleague', text='x')
    ledger.move(t, it, 'sent')
    with pytest.raises(ledger.IllegalMoveError):
        ledger.move(t, it, 'awaiting_owner')
    with pytest.raises(machine.IllegalStateError):
        machine.begin_turn(t, 'owner', 'thread')  # the colleague's turn is still running
    with pytest.raises(machine.IllegalStateError):
        machine.open_case(t, 'D_OWNER', '1.0', 'own')  # it has one


def test_the_owner_asking_in_the_colleagues_thread_is_answered_in_that_thread(case, fresh_bot):
    """Each message is answered where it was written: the owner's word in Salah's thread is answered there, not in
    the owner's DM, and is in the case like everyone's."""
    t, sent = case
    tasks.follow_up(t, '<@BCOMPANION> bro why is there n+1', None, '60.3', 'thread')
    assert (t['turn']['by'], t['turn']['place'], machine.final_goes_to(t)) == ('owner', 'thread', 'thread')
    assert 'your final message is posted there, so Salah reads it' in sent[-1]
    fresh_bot.messages.clear()
    tasks.follow_up(t, '<@BCOMPANION> updates?', None, '60.4', 'thread')
    side = [m for m in posted(fresh_bot, SALAH_DM, '60.1') if 'It is checking the stack.' in text_of(m)]
    assert side and 'Side answer' in text_of(side)
    assert not any('Side answer' in text_of(m) for m in posted(fresh_bot, 'D_OWNER'))
    owners = [i for i in ledger.items(t) if i['kind'] == 'in' and i.get('by') == OWNER]
    assert [i['text'] for i in owners] == ['bro why is there n+1', 'updates?']
    assert ledger.items(t)[-1]['to'] == 'colleague' and ledger.items(t)[-1]['side']


def test_the_owner_asking_privately_is_answered_privately(case, fresh_bot):
    t, _ = case
    tasks.follow_up(t, 'status?', None, '61.5', 'case')
    assert any('It is checking the stack.' in text_of(m) for m in posted(fresh_bot, 'D_OWNER', t['case']['ts']))
    assert not any('It is checking the stack.' in text_of(m) for m in posted(fresh_bot, SALAH_DM))


def test_the_thinking_line_is_edited_where_it_was_posted_and_follows_the_turn(case, fresh_bot, monkeypatch):
    t, _ = case
    assert t['line']['ch'] == SALAH_DM
    old = t['line']['ts']
    tasks.follow_up(t, 'look at the logs first', None, '61.6', 'case')  # the owner, privately, mid-turn
    assert t['line']['ch'] == 'D_OWNER' and any(u['channel'] == SALAH_DM and u['ts'] == old for u in fresh_bot.updates)
    fresh_bot.updates.clear()
    monkeypatch.setattr(t3, 'snapshot', snapshot('running', 'Reading the logs', running=True))
    monkeypatch.setattr(tasks, 'STATUS_EVERY', 0)
    tasks.tick(t)
    assert fresh_bot.updates and all(u['channel'] == 'D_OWNER' for u in fresh_bot.updates)


@pytest.mark.usefixtures('case')
def test_an_edit_that_adds_the_tag_is_a_message_to_the_companion(monkeypatch):
    set_settings({'access': ['U_SALAH']})
    calls = []
    monkeypatch.setattr(tasks, 'follow_up', lambda task, text, files, ts, place, by=None: calls.append((ts, by)))
    msg = {'ts': '60.7', 'thread_ts': '60.1', 'user': 'U_SALAH'}
    edit = {'channel': SALAH_DM, 'subtype': 'message_changed', 'channel_type': 'im'}
    routing.route(
        dict(edit, message=dict(msg, text='updates? (typo fixed)'), previous_message=dict(msg, text='x')), False
    )
    assert calls == []  # an edit without a new tag changes nothing
    tagged = dict(edit, message=dict(msg, text='<@BCOMPANION> updates?'), previous_message=dict(msg, text='updates?'))
    routing.route(tagged, False)
    routing.route(tagged, False)  # Slack may send it twice
    assert calls == [('60.7', 'U_SALAH')]


def test_a_case_in_a_thread_syncs_the_whole_thread_and_an_ask_written_before_the_tag(monkeypatch, t3_quiet, fresh_bot):
    """Ali's case from #engineering-core: the thread so far, his ask in a message of its own, then "@leafy" alone."""
    set_settings({'access': ['U_SALAH']})
    monkeypatch.setattr(t3, 'send', lambda tid, msg: {'ok': True})
    monkeypatch.setattr(tasks, 'history_with', lambda uid, now=None: [])
    thread = [
        {'ts': '70.1', 'user': 'U_ALI', 'text': 'Vercel Board looks neat'},
        {'ts': '70.2', 'user': 'U_SALAH', 'text': 'compare it with the rust one'},
        {'ts': '70.3', 'user': 'U_SALAH', 'text': 'its readme is too long, please read it all'},
        {'ts': '70.4', 'user': 'U_SALAH', 'text': '<@BCOMPANION>'},
    ]
    monkeypatch.setattr(slack, 'thread_messages', lambda ch, tts, trigger: thread)
    tasks.start('C_TECH', '70.1', '70.4', '<@BCOMPANION>', guest='U_SALAH')
    t = state.state['tasks'][state.key('C_TECH', '70.1')]
    said = [(i['label'], i['text']) for i in ledger.items(t) if i['kind'] == 'in']
    assert said == [
        ('Ali', 'Vercel Board looks neat'),
        ('Salah', 'compare it with the rust one\nits readme is too long, please read it all'),
    ]
    assert t['title'].startswith('compare it with the rust one')
    case = in_case(fresh_bot, t)
    assert 'Earlier in the thread' in case and 'Vercel Board looks neat' in case

    fresh_bot.messages.clear()
    routing.route({'channel': 'C_TECH', 'ts': '70.6', 'thread_ts': '70.1', 'user': 'U_ALI', 'text': 'nice'}, False)
    later = {'channel': 'C_TECH', 'ts': '70.7', 'thread_ts': '70.1', 'user': 'U_SALAH', 'text': '<@BCOMPANION>'}
    routing.route(later, True)
    routing.route(dict(later), True)  # Slack sends a tag as app_mention and as message
    news = [(i['label'], i['text']) for i in ledger.items(t) if i['kind'] == 'in'][2:]
    assert news == [('Ali', 'nice'), ('Salah', '(tagged Companion)')]
    case = in_case(fresh_bot, t)
    assert 'nice' in case and '(tagged Companion)' in case
