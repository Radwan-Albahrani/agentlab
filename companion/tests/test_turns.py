import pytest
from bot import ledger, machine, slack, state, t3, tasks
from conftest import OWNER, set_settings


def task(running=True, who=None, kind='owner', case=None, outcome='answered', **extra):
    """A task in the middle of a turn (`running`), or after one that ended with `outcome`."""
    now = state.now_iso()
    t = {
        'thread': 'T1',
        'title': 'Check the queue',
        'project': '/workspace/platform',
        'channel': 'C9',
        'thread_ts': '9.1',
        'outbox': 'x',
        'trigger_ts': '9.1',
        'status_ts': 'ts9',
        'start': now,
        'burst_start': now,
        'seen': '',
        'step_from': '',
        'asked': [],
        'prs': [],
        'workers_said': 0,
        'last_status': '',
        'last_status_at': 0,
        'quiet_since': 0,
        'options': {},
        'party': {'kind': kind, 'user': who or OWNER},
        **extra,
    }
    if case:
        t['case'] = case
    t['turn'] = {
        'n': 1,
        'by': 'owner' if kind == 'owner' else 'colleague',
        'state': 'running' if running else 'ended',
        'outcome': '' if running else outcome,
        'at': 0,
        'ended': 0,
    }
    machine.settle(t)
    state.state['tasks'][state.key(t['channel'], t['thread_ts'])] = t
    return t


def snapshot(status, answer=None):
    messages = [('m1', state.now_iso(), answer)] if answer else []
    return lambda tid, since: {
        'running': False,
        'last_status': status,
        'last_done': state.now_iso(),
        'messages': messages,
        'requests': [],
        'workers': [],
        'prs': [],
    }


def test_a_finished_turn_posts_the_answer(monkeypatch, t3_quiet, fresh_bot):
    monkeypatch.setattr(t3, 'snapshot', snapshot('completed', 'The queue is empty.'))
    t = task()
    tasks.tick(t)
    assert not machine.running(t) and machine.outcome(t) == 'answered' and t['phase'] == 'answered'
    assert 'queue is empty' in fresh_bot.text()
    assert [(i['kind'], i['to'], i['state']) for i in ledger.items(t)] == [('final', 'thread', 'sent')]


def test_a_turn_ending_in_a_question_answered_by_message_closes_and_asks(monkeypatch, t3_quiet, fresh_bot):
    ask = snapshot('completed', 'Could you send a link to the new feedback?')
    item = {'questions': [{'question': 'Which one?', 'options': [{'label': 'Staging'}, {'label': 'Prod'}]}]}
    monkeypatch.setattr(t3, 'snapshot', lambda tid, since: {**ask(tid, since), 'asked': [item]})
    t = task()
    tasks.tick(t)
    assert not machine.running(t) and machine.outcome(t) == 'asked' and t['phase'] == 'waiting_answer'
    assert t['question'] and t['options'] == {'1': 'Staging', '2': 'Prod'}
    assert 'send a link' in fresh_bot.text() and 'Staging' in fresh_bot.text()


def test_a_busy_model_gets_an_automatic_continue(monkeypatch, t3_quiet):
    monkeypatch.setattr(t3, 'snapshot', snapshot('failed'))
    monkeypatch.setattr(t3, 'run_error', lambda tid: '{"message": "Selected model is at capacity"}')
    t = task()
    tasks.tick(t)
    assert machine.running(t) and t['retry_at'] and t['retries'] == 1


def test_with_auto_retry_off_the_failure_is_reported(monkeypatch, t3_quiet):
    set_settings({'auto_retry': False})
    monkeypatch.setattr(t3, 'snapshot', snapshot('failed'))
    monkeypatch.setattr(t3, 'run_error', lambda tid: '{"message": "Selected model is at capacity"}')
    t = task()
    tasks.tick(t)
    assert not machine.running(t) and machine.outcome(t) == 'failed' and t['phase'] == 'failed'


def test_an_errand_that_needs_nothing_closes_quietly(monkeypatch, t3_quiet, fresh_bot):
    monkeypatch.setattr(t3, 'snapshot', snapshot('completed', 'NO_ACTION: only Sam can decide this'))
    t = task(
        who='U_SALAH',
        kind='errand',
        channel='D_OWNER',
        case={'ch': 'D_OWNER', 'ts': '9.1', 'head': 'errand', 'mode': 'private'},
    )
    tasks.tick(t)
    assert machine.outcome(t) == 'nothing_to_do' and t['phase'] == 'nothing_to_do'
    assert t['closed'].endswith('Nothing needed')
    assert not fresh_bot.messages
    assert ledger.items(t)[-1]['state'] == 'silent' and ledger.items(t)[-1]['text'] == 'only Sam can decide this'


def test_a_turn_with_nothing_new_posts_nothing(monkeypatch, t3_quiet, fresh_bot):
    monkeypatch.setattr(t3, 'snapshot', snapshot('completed', 'NO_REPLY: edited the earlier reply to add #6291'))
    t = task()
    tasks.tick(t)
    assert not machine.running(t) and machine.outcome(t) == 'silent'
    assert 'NO_REPLY' not in fresh_bot.text() and '6291' not in fresh_bot.text()


@pytest.mark.parametrize(
    'message, is_status',
    [
        ('status?', True),
        ("how's it going", True),
        ('any update?', True),
        ("what's going on?", True),
        ('where is it at', True),
        ('updates?', True),
        ('update', True),
        ('any news?', True),
        ('push the updates', False),
        ('fix the status badge', False),
        ('check the status page and update the docs please now', False),
    ],
)
def test_status_questions_are_told_apart_from_instructions(message, is_status):
    assert tasks.is_status_ask(message) is is_status


def test_a_child_cut_off_by_a_restart_holds_the_turn_until_t3_resumes_it(monkeypatch, t3_quiet, fresh_bot):
    # the lead ended its turn waiting on QA; a restart interrupted QA's run: nothing is over yet
    cut = state.now_iso()
    waiting = snapshot('completed', 'Waiting on the QA child thread.')
    monkeypatch.setattr(t3, 'snapshot', lambda tid, since: {**waiting(tid, since), 'interrupted_at': cut})
    t = task()
    tasks.tick(t)
    assert machine.running(t) and 'Waiting on the QA' not in fresh_bot.text()


def test_a_cut_off_run_that_t3_never_resumes_ends_the_turn_after_the_grace(monkeypatch, t3_quiet):
    cut = '2026-01-01T00:00:00Z'  # long past RESUME_GRACE
    done = snapshot('completed', 'Waiting on the QA child thread.')
    monkeypatch.setattr(t3, 'snapshot', lambda tid, since: {**done(tid, since), 'interrupted_at': cut})
    t = task()
    tasks.tick(t)
    assert not machine.running(t)


def test_nothing_is_concluded_while_the_agent_is_down(monkeypatch, t3_quiet):
    monkeypatch.setattr(t3, 'snapshot', snapshot('completed', 'Done.'))
    monkeypatch.setattr(t3, 'agent_up', lambda: False)
    t = task()
    tasks.tick(t)
    assert machine.running(t) and t['down_since']
    t['down_since'] -= tasks.AGENT_DOWN_LIMIT + 1  # down for too long: decide as before
    tasks.tick(t)
    assert not machine.running(t) and machine.outcome(t) == 'answered'


def test_history_lists_what_was_done_with_the_person_lately(monkeypatch):
    set_settings({'github_people': [{'github': 'salah-gh', 'slack': 'U_SALAH'}]})
    now = state.parse_iso(state.now_iso())
    review = {'id': 'org/platform#6257', 'title': 'group trees', 'author': 'Salah-GH', 'asked_by': []}
    task(False, channel='C1', thread_ts='1.1', thread='T_R', review=review)
    task(False, 'U_SALAH', 'colleague', channel='C1', thread_ts='2.1', thread='T_G', title='Fix the export')
    task(False, 'U_ALI', 'colleague', channel='C1', thread_ts='3.1', thread='T_OTHER', title='Not Salah')
    task(False, 'U_SALAH', 'colleague', channel='C1', thread_ts='4.1', thread='T_OLD', start='2026-01-01T00:00:00Z')
    task(True, 'U_SALAH', 'colleague', channel='C1', thread_ts='5.1', thread='T_NOW', title='Still going')
    lines = tasks.history_with('U_SALAH', now)
    assert len(lines) == 3
    assert 'Reviewed org/platform#6257 (group trees): answered · T3 chat T_R' in lines[0]
    assert 'Task "Fix the export": answered · T3 chat T_G' in lines[1]
    assert 'Task "Still going": in progress · T3 chat T_NOW' in lines[2]


def test_a_new_message_in_a_dm_sees_the_last_days_and_its_history(monkeypatch, t3_quiet):
    calls, prompts_sent = [], []

    def history(**kw):
        calls.append(kw)
        return {'messages': [{'ts': '80.1', 'user': 'U_SALAH', 'text': 'I fixed them'}]}

    monkeypatch.setattr(slack.app.client, 'conversations_history', history)
    monkeypatch.setattr(
        t3, 'start_thread', lambda project, title, message: prompts_sent.append(message) or ('T_NEW', '')
    )
    monkeypatch.setattr(tasks, 'history_with', lambda uid, now=None: ['- [9:58 AM] Reviewed org/p#6257: posted'])
    tasks.start('D_U_SALAH', '80.1', '80.1', 'I fixed them', guest='U_SALAH')
    assert float(calls[0]['latest']) - float(calls[0]['oldest']) == 3 * 86400 and calls[0]['limit'] == 20
    assert 'the 3 days before it' in prompts_sent[0] and 'Reviewed org/p#6257' in prompts_sent[0]


@pytest.mark.parametrize('ask', ['status?', 'btw did you run the e2e tests?', '/btw which branch?'])
@pytest.mark.parametrize('busy', [True, False])
def test_a_side_question_is_answered_by_the_quick_model_and_never_reaches_the_chat(
    monkeypatch, t3_quiet, fresh_bot, ask, busy
):
    sent, asked = [], []
    monkeypatch.setattr(t3, 'busy', lambda tid: busy)
    monkeypatch.setattr(t3, 'send', lambda tid, msg: sent.append(msg) or {'ok': True})
    monkeypatch.setattr(t3, 'digest', lambda tid: 'Running: yes\n- reasoning: running the e2e tests')
    monkeypatch.setattr(
        t3, 'triage', lambda prompt: asked.append(prompt) or {'ok': True, 'result': 'Running the e2e tests.'}
    )
    t = task(running=busy)
    turn = dict(t['turn'])
    tasks.follow_up(t, ask, None, '9.5')
    assert not sent and 'running the e2e tests' in asked[0] and 'btw' not in asked[0].split('Question: ')[1][:8]
    assert 'Running the e2e tests.' in fresh_bot.text() and "the agent wasn't interrupted" in fresh_bot.text()
    assert t['turn'] == turn  # a side answer is no turn


def test_without_the_quick_model_a_status_ask_gets_the_plain_summary(monkeypatch, t3_quiet, fresh_bot):
    monkeypatch.setattr(t3, 'digest', lambda tid: '')
    monkeypatch.setattr(t3, 'triage', lambda prompt: {'ok': False, 'error': 'down'})
    monkeypatch.setattr(t3, 'snapshot', lambda tid, since: {**snapshot('completed', 'x')(tid, since), 'running': True})
    monkeypatch.setattr(t3, 'open_run_since', lambda tid: None)
    monkeypatch.setattr(t3, 'last_answer', lambda tid: 'Half way through the migration.')
    tasks.follow_up(task(), 'status?', None, '9.6')
    assert 'Half way through the migration' in fresh_bot.text()


def test_a_colleagues_side_question_and_its_answer_reach_the_owners_case(monkeypatch, t3_quiet, fresh_bot):
    monkeypatch.setattr(t3, 'digest', lambda tid: 'r')
    monkeypatch.setattr(t3, 'triage', lambda prompt: {'ok': True, 'result': 'Reviewing PR 6257.'})
    t = task(
        True,
        'U_SALAH',
        'colleague',
        channel='D_U_SALAH',
        thread_ts='60.1',
        case={'ch': 'D_OWNER', 'ts': '61.1', 'head': 'own', 'mode': 'private'},
    )
    tasks.follow_up(t, 'any update?', None, '60.5', 'U_SALAH')
    in_case = [m for m in fresh_bot.messages if m['channel'] == 'D_OWNER' and m.get('thread_ts') == '61.1']
    assert 'any update?' in str(in_case) and 'Reviewing PR 6257.' in str(in_case)
    assert any(m['channel'] == 'D_U_SALAH' and 'Reviewing PR 6257.' in str(m) for m in fresh_bot.messages)


@pytest.mark.parametrize('delivery', ['queued', 'started'])
def test_a_follow_up_that_waits_behind_the_running_turn_says_so(monkeypatch, t3_quiet, fresh_bot, delivery):
    monkeypatch.setattr(t3, 'send', lambda tid, msg: {'ok': True, 'result': {'delivery': delivery}})
    monkeypatch.setattr(t3, 'digest', lambda tid: 'r')
    monkeypatch.setattr(t3, 'triage', lambda prompt: {'ok': True, 'result': 'Running the deep reviews.'})
    tasks.follow_up(task(), 'the table looks broken on mobile', None, '9.7')
    told = 'Queued: the agent reads this when its current step ends. Right now: Running the deep reviews.'
    assert (told in fresh_bot.text()) is (delivery == 'queued')
