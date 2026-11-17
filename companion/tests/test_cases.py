"""Cases: a colleague's conversation with the companion, followed by the owner from a thread in their DM."""

import json
import os

import pytest
from bot import errands, jobs, outbox, routing, slack, state, t3, tasks
from conftest import OWNER

SALAH_DM = 'D_U_SALAH'  # Salah's DM with the bot


def snapshot(status, answer):
    return lambda tid, since: {
        'running': False,
        'last_status': status,
        'last_done': state.now_iso(),
        'messages': [('m1', state.now_iso(), answer)],
        'requests': [],
        'workers': [],
        'prs': [],
    }


@pytest.fixture
def case(monkeypatch, t3_quiet, fresh_bot):
    """Salah messaged the bot in his DM: his task, with its case head in the owner's DM."""
    sent = []
    monkeypatch.setattr(t3, 'send', lambda tid, msg: sent.append(msg) or {'ok': True})
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
    return json.dumps(msgs)


def test_a_colleagues_message_opens_a_case_in_the_owners_dm(case, fresh_bot):
    t, _ = case
    head = t['case']
    assert head['ch'] == 'D_OWNER' and head['own']
    first = next(m for m in fresh_bot.messages if m.get('ts') is None and m['channel'] == 'D_OWNER')
    assert 'Salah' in text_of(first) and 'I fixed them' in text_of(first)


def test_their_turn_is_answered_in_their_thread_and_copied_to_the_case(case, fresh_bot, monkeypatch):
    t, _ = case
    monkeypatch.setattr(t3, 'snapshot', snapshot('completed', 'All 16 PRs check out.'))
    tasks.tick(t)
    assert 'All 16 PRs' in text_of(posted(fresh_bot, SALAH_DM, '60.1'))
    copy = text_of(posted(fresh_bot, 'D_OWNER', t['case']['ts']))
    assert 'All 16 PRs' in copy and 'Salah' in copy


def test_the_owner_talks_to_the_agent_privately_in_the_case(case, fresh_bot, monkeypatch):
    t, sent = case
    t['active'] = False
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
    assert sent[-1].startswith('Radwan') or 'private' in sent[-1]
    assert 'is the engine real?' in sent[-1] and 'sees none of this' in sent[-1]
    monkeypatch.setattr(t3, 'snapshot', snapshot('completed', 'No: the engine repo does not exist.'))
    tasks.tick(t)
    assert 'engine repo' in text_of(posted(fresh_bot, 'D_OWNER', t['case']['ts']))
    assert len(posted(fresh_bot, SALAH_DM)) == before  # nothing reached Salah, not even a thinking line
    assert 'answer_to' not in t and not t['active']


def test_on_the_owners_word_the_agent_sends_the_colleague_a_message(case, fresh_bot):
    t, _ = case
    box = os.path.join(outbox.OUTBOX, t['outbox'])
    os.makedirs(box, exist_ok=True)
    with open(os.path.join(box, 'send.json'), 'w') as f:
        json.dump({'text': 'The stack is on hold until the engine is in a repo we can see.'}, f)
    outbox.tick(t)
    assert 'on hold' in text_of(posted(fresh_bot, SALAH_DM, '60.1'))
    assert 'Sent to Salah' in text_of(posted(fresh_bot, 'D_OWNER', t['case']['ts']))
    assert not os.path.exists(os.path.join(box, 'send.json'))


def test_a_colleague_writing_while_the_owner_talks_waits_its_turn(case, fresh_bot, monkeypatch):
    t, sent = case
    t['active'] = False
    routing.route(
        {
            'channel': 'D_OWNER',
            'channel_type': 'im',
            'ts': '91.1',
            'thread_ts': t['case']['ts'],
            'user': OWNER,
            'text': 'hold on',
        },
        False,
    )
    n = len(sent)
    tasks.follow_up(t, 'any news?', None, '92.1', 'U_SALAH')
    assert len(sent) == n and t['queue'][0]['text'] == 'any news?'
    assert 'any news?' in text_of(posted(fresh_bot, 'D_OWNER', t['case']['ts']))  # the owner sees it at once
    monkeypatch.setattr(t3, 'snapshot', snapshot('completed', 'Holding.'))
    tasks.tick(t)  # the owner's turn ends: Salah's message goes to the agent now, as his turn
    assert len(sent) == n + 1 and 'Salah' in sent[-1] and 'any news?' in sent[-1] and 'answer_to' not in t


def test_a_turn_the_owner_starts_in_t3_answers_the_owner(case, fresh_bot, monkeypatch):
    t, _ = case
    t['active'] = False
    monkeypatch.setattr(t3, 'has_open_run', lambda tid: True)
    monkeypatch.setattr(t3, 'snapshot', lambda tid, since: {**snapshot('completed', 'x')(tid, since), 'running': True})
    tasks.tick(t)
    assert t['answer_to'] == {'ch': 'D_OWNER', 'tts': t['case']['ts']}


def test_approvals_go_in_the_case_and_a_newer_one_replaces_the_old(case, fresh_bot):
    t, _ = case
    errands.ask_approval(t, {'action': 'Merge the stack', 'details': 'x'})
    first = t['approval']
    assert first['ch'] == 'D_OWNER' and posted(fresh_bot, 'D_OWNER', t['case']['ts'])
    errands.ask_approval(t, {'action': 'Merge only #6257', 'details': 'y'})
    assert t['approval']['action'] == 'Merge only #6257' and first['decided'] == 'replaced'
    assert 'Replaced by a newer request' in fresh_bot.text()
    errands.decide(t, 'k', True, card=first['ts'])  # the old card's button decides nothing
    assert not t['approval']['decided']


def test_the_agent_can_withdraw_its_approval_request(case, fresh_bot):
    t, _ = case
    errands.ask_approval(t, {'action': 'Merge the stack', 'details': 'x'})
    errands.ask_approval(t, {'withdraw': 'the engine is not in a repo yet'})
    assert t['approval']['decided'] == 'replaced' and 'Withdrawn by' in fresh_bot.text()
    errands.decide(t, 'k', True)
    assert t['approval']['decided'] == 'replaced'  # nothing left to approve
