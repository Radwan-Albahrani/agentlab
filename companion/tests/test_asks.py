import json
import os
import time
from datetime import datetime, timedelta

import pytest
from bot import asks, config, ledger, machine, outbox, polls, posts, projects, publish, state, t3, tasks
from bot.when import say
from conftest import OWNER, agent_sends, click, ended, receipts

IN_AN_HOUR = (datetime.now().astimezone() + timedelta(hours=1)).isoformat()


def drop_ask(**ask):
    with open(os.path.join(config.COMP.asks_dir, f'{time.time_ns()}.json'), 'w') as f:
        json.dump(ask, f)


@pytest.fixture
def started(t3_quiet, monkeypatch):
    """Start an ask via the asks folder -> (task, outbox, prompt sent)."""
    told = []
    monkeypatch.setattr(t3, 'start_thread', lambda project, title, message: told.append(message) or ('T_ASK', ''))

    def start(**ask):
        drop_ask(**ask)
        asks.tick()
        (task,) = state.state['tasks'].values()
        box = os.path.join(outbox.OUTBOX, task['outbox'])
        os.makedirs(box, exist_ok=True)
        return task, box, told[0]

    return start


def channel_posts(bot, channel):
    return [m for m in bot.messages if m['channel'] == channel]


def to_tech(text, **more):
    return {'type': 'message', 'to': '#ask-tech', 'text': text, **more}


def test_an_ask_is_taken_once_and_starts_the_agent_in_the_owners_dm(started, fresh_bot):
    task, _, told = started(text='Announce the deploy freeze on Thursday', channel='C_TECH', review=True)
    assert task['channel'] == 'D_OWNER' and task['thread'] == 'T_ASK'
    assert 'deploy freeze' in told and 'C_TECH' in told and '#ask-tech' in told and 'send.json' in told
    assert '"type"' in told and 'receipts.json' in told
    assert os.listdir(config.COMP.asks_dir) == []
    assert 'From the hub' in fresh_bot.text()
    assert machine.running(task) and task['party'] == {'kind': 'owner', 'user': OWNER}


def test_a_post_waits_for_the_owners_tap_and_only_the_owner_can_give_it(started, fresh_bot):
    task, _, _ = started(text='Announce the freeze', channel='C_TECH', review=True)
    agent_sends(task, to_tech('Deploy freeze on Thursday.'))
    assert channel_posts(fresh_bot, 'C_TECH') == []
    (it,) = ledger.pending(task)
    assert it['state'] == 'awaiting_owner' and publish.card('k', task)['waiting'] == 'post'
    click(fresh_bot, 'post_send', user='U_SALAH')
    assert channel_posts(fresh_bot, 'C_TECH') == [] and it['state'] == 'awaiting_owner'
    click(fresh_bot, 'post_send')
    assert channel_posts(fresh_bot, 'C_TECH')[0]['text'] == 'Deploy freeze on Thursday.'
    assert [h[0] for h in it['history']] == ['received', 'awaiting_owner', 'approved', 'sent']


def test_dont_post_posts_nothing(started, fresh_bot):
    task, box, _ = started(text='x', channel='C_TECH', review=True)
    agent_sends(task, to_tech('Hello'))
    click(fresh_bot, 'post_skip')
    assert channel_posts(fresh_bot, 'C_TECH') == []
    last = receipts(box)[-1]
    assert last['state'] == 'rejected' and last['meaning'] == 'rejected by the owner'


def test_without_review_it_goes_out_at_once(started, fresh_bot):
    task, _, _ = started(text='x', channel='C_TECH', review=False)
    agent_sends(task, to_tech('Hello all'))
    assert channel_posts(fresh_bot, 'C_TECH')[0]['text'] == 'Hello all'


def test_a_channel_companion_is_not_in_is_refused_with_how_to_fix_it(started, fresh_bot):
    task, box, _ = started(text='x', channel='', review=False)
    agent_sends(task, {'type': 'message', 'to': 'C_ELSEWHERE', 'text': 'Hello'})
    assert channel_posts(fresh_bot, 'C_ELSEWHERE') == []
    assert '/invite @Companion' in receipts(box)[-1]['note']
    assert '/invite @Companion' in fresh_bot.text()  # and the owner is told where they follow the task


def test_two_posts_wait_side_by_side_and_each_card_decides_its_own(started, fresh_bot):
    task, _, _ = started(text='x', channel='C_TECH', review=True)
    agent_sends(task, to_tech('First'), to_tech('Second'))
    assert len(ledger.pending(task)) == 2
    click(fresh_bot, 'post_send', nth=1)
    click(fresh_bot, 'post_skip', nth=0)
    assert [m['text'] for m in channel_posts(fresh_bot, 'C_TECH')] == ['Second']
    assert [i['state'] for i in ledger.items(task)] == ['rejected', 'sent']


@pytest.mark.parametrize(
    ('item', 'why'),
    [
        ({'to': '#ask-tech', 'text': 'x'}, '"type" must be one of'),
        ({'type': 'message', 'text': 'x'}, '"to" is required'),
        ({'type': 'message', 'to': '#ask-tech'}, 'no text and no files'),
        ({'type': 'approval', 'details': 'x'}, 'needs an "action"'),
        ({'type': 'edit', 'id': '9', 'text': 'x'}, 'names no message this task sent'),
    ],
)
def test_an_item_that_says_too_little_is_refused_never_guessed(started, fresh_bot, item, why):
    task, box, _ = started(text='x', channel='C_TECH', review=True)
    agent_sends(task, item)
    (r,) = receipts(box)
    assert r['state'] == 'refused' and why in r['note']
    assert channel_posts(fresh_bot, 'C_TECH') == []


@pytest.mark.parametrize(
    ('poll', 'problem'),
    [
        ({'question': 'Lunch?', 'options': ['Pizza'], 'closes': IN_AN_HOUR}, '2 to 10'),
        ({'question': 'Lunch?', 'options': ['A', 'B'], 'closes': 'tomorrow'}, 'ISO 8601'),
        ({'question': 'Lunch?', 'options': ['A', 'B'], 'closes': '2020-01-01T10:00:00+03:00'}, 'in the future'),
    ],
)
def test_a_bad_poll_is_refused(poll, problem):
    post, why = posts.parse({'channel': 'C_TECH', 'poll': poll})
    assert post is None and problem in why


@pytest.fixture
def poll(started, fresh_bot):
    task, _, _ = started(text='Lunch poll', channel='C_RANDOM', review=False)
    agent_sends(
        task,
        {
            'type': 'message',
            'to': '#random',
            'text': 'Team lunch on Thursday!',
            'poll': {'question': 'Where?', 'options': ['Pizza', 'Shawarma', 'Sushi'], 'closes': IN_AN_HOUR},
        },
    )
    (p,) = state.state['polls'].values()
    return task, p


def vote(p, user, option):
    i = p['options'].index(option)
    polls.on_vote(lambda: None, {'actions': [{'value': f'{p["id"]}:{i}'}], 'user': {'id': user}})


def test_anyone_can_vote_once_and_take_it_back(poll, fresh_bot):
    task, p = poll
    assert ['poll_vote_0', 'poll_vote_1', 'poll_vote_2'] in fresh_bot.actions()
    vote(p, 'U_A', 'Pizza')
    vote(p, 'U_B', 'Pizza')
    vote(p, 'U_A', 'Sushi')
    assert polls.counts(p) == [1, 0, 1]
    vote(p, 'U_B', 'Pizza')
    assert polls.counts(p) == [0, 0, 1]
    assert '1 vote' in json.dumps(fresh_bot.updates[-1])
    assert publish.card('k', task)['status'] == 'working' and 'Poll open' in publish.card('k', task)['outcome']


def test_the_poll_closes_on_time_and_announces_the_winner(poll, fresh_bot):
    task, p = poll
    vote(p, 'U_A', 'Shawarma')
    vote(p, 'U_B', 'Shawarma')
    vote(p, 'U_C', 'Pizza')
    polls.tick()
    assert p['open']
    p['closes'] = time.time() - 1
    polls.tick()
    assert not p['open']
    announce = channel_posts(fresh_bot, 'C_RANDOM')[-1]
    assert announce['thread_ts'] == p['ts'] and announce['reply_broadcast']
    assert '**Shawarma** wins with 2 of 3 votes' in json.dumps(announce['blocks'])
    vote(p, 'U_D', 'Pizza')
    assert polls.counts(p) == [1, 2, 0]
    ended(task)
    assert publish.card('k', task)['status'] == 'done'


def test_a_tie_and_an_empty_poll_say_so(poll):
    _, p = poll
    assert 'no votes' in polls.result(p)
    vote(p, 'U_A', 'Pizza')
    vote(p, 'U_B', 'Sushi')
    assert 'A tie between **Pizza** and **Sushi**' in polls.result(p)


def test_only_the_owner_can_close_a_poll_early(poll):
    _, p = poll
    body = {'actions': [{'value': p['id']}], 'channel': {'id': 'D_OWNER'}, 'container': {'message_ts': '1.0'}}
    polls.on_close(lambda: None, {**body, 'user': {'id': 'U_SALAH'}})
    assert p['open']
    polls.on_close(lambda: None, {**body, 'user': {'id': OWNER}})
    assert not p['open']


@pytest.fixture
def tagged(t3_quiet, monkeypatch):
    told = []
    monkeypatch.setattr(t3, 'start_thread', lambda project, title, message: told.append(message) or ('T_TAG', ''))
    monkeypatch.setattr(projects, '_profiles', dict)
    tasks.start('C_RANDOM', '70.1', '70.2', '<@BCOMPANION> make a poll ends at 2pm')
    task = state.state['tasks'][state.key('C_RANDOM', '70.1')]
    box = os.path.join(outbox.OUTBOX, task['outbox'])
    os.makedirs(box, exist_ok=True)
    return task, box, told[0]


LUNCH = {
    'type': 'message',
    'to': '#random',
    'text': 'Lunch on Thursday: pick a place!\n- Peradiz (Indian): https://maps.app.goo.gl/kRDMYyC9x8qAdJpYA',
    'poll': {'question': 'Where do we eat?', 'options': ['Peradiz (Indian)', 'Fatto (Italian)'], 'closes': IN_AN_HOUR},
}


def test_the_agent_is_told_it_can_post_here_without_a_preview(tagged):
    _, _, told = tagged
    assert 'send.json' in told and 'C_RANDOM' in told and '"thread": this thread, at once' in told
    assert 'Messages to this channel go at once' in told


def test_a_poll_asked_for_in_a_channel_is_a_new_message_there_at_once(tagged, fresh_bot):
    task, _, _ = tagged
    agent_sends(task, LUNCH)
    (p,) = state.state['polls'].values()
    poll_msg = next(m for m in fresh_bot.messages if m['channel'] == 'C_RANDOM' and m.get('text') == 'Where do we eat?')
    assert 'thread_ts' not in poll_msg
    assert 'post_send' not in json.dumps(fresh_bot.actions())
    in_thread = [m for m in fresh_bot.messages if m['channel'] == 'C_RANDOM' and m.get('thread_ts') == '70.1']
    assert 'Poll posted in #' in json.dumps(in_thread)
    owner_dm = [m for m in fresh_bot.messages if m['channel'] == 'D_OWNER']
    assert ['poll_close'] in [
        [e['action_id'] for b in m['blocks'] if b['type'] == 'actions' for e in b['elements']] for m in owner_dm
    ]
    assert p['channel'] == 'C_RANDOM'


def test_once_posted_the_agent_says_so_or_stays_silent_on_purpose(tagged, fresh_bot):
    task, _, _ = tagged
    agent_sends(task, LUNCH)
    before = len(fresh_bot.messages)
    task['latest'] = 'NO_REPLY: the poll is up'
    tasks._finish_turn(task, {'last_status': 'completed', 'last_done': None})
    assert len(fresh_bot.messages) == before
    assert machine.outcome(task) == 'silent' and ledger.items(task)[-1]['state'] == 'silent'


def test_a_post_for_another_channel_still_asks_first(tagged, fresh_bot):
    task, _, _ = tagged
    agent_sends(task, to_tech('Hello tech'))
    assert channel_posts(fresh_bot, 'C_TECH') == []
    assert ['post_send', 'post_skip'] in fresh_bot.actions()


def test_a_message_by_dm_is_previewed_even_when_asked_in_the_channel(tagged, fresh_bot):
    task, _, told = tagged
    assert '"to"' in told
    agent_sends(
        task, {'type': 'message', 'to': ['Ali', 'Ali Khan'], 'text': 'Sam asked me to let you know: lunch at 2.'}
    )
    assert channel_posts(fresh_bot, 'D_U_ALI') == []
    assert '<@U_ALI>, <@U_ALI2> by DM' in fresh_bot.text()
    click(fresh_bot, 'post_send')
    assert channel_posts(fresh_bot, 'D_U_ALI')[0]['text'].startswith('Sam asked me')
    assert channel_posts(fresh_bot, 'D_U_ALI2')
    assert 'Message sent to Ali, Ali Khan by DM' in fresh_bot.text()


def test_an_unclear_person_is_refused_with_why(tagged, fresh_bot):
    task, _, _ = tagged
    agent_sends(task, {'type': 'message', 'to': 'Al', 'text': 'Hi'})
    assert 'matches 2 people' in fresh_bot.text()
    assert 'post_send' not in json.dumps(fresh_bot.actions())


def test_multiple_choice_lets_people_pick_several_and_take_one_back(started, fresh_bot):
    task, _, _ = started(text='x', channel='C_RANDOM', review=False)
    agent_sends(
        task,
        {
            'type': 'message',
            'to': '#random',
            'text': '',
            'poll': {
                'question': 'Which days?',
                'options': ['Mon', 'Tue', 'Wed'],
                'closes': IN_AN_HOUR,
                'multiple': True,
            },
        },
    )
    (p,) = state.state['polls'].values()
    vote(p, 'U_A', 'Mon')
    vote(p, 'U_A', 'Wed')
    vote(p, 'U_B', 'Wed')
    assert polls.counts(p) == [1, 0, 2] and polls.voters(p) == 2
    vote(p, 'U_A', 'Mon')
    assert p['votes']['U_A'] == [2]
    assert 'pick as many as you like' in json.dumps(fresh_bot.updates[-1])
    assert '**Wed** wins: 2 of the 2 people who voted picked it' in polls.result(p)


def test_polls_from_before_become_multiple_choice_and_keep_their_votes(poll, fresh_bot):
    _, p = poll
    p.pop('multiple')
    p['votes'] = {'U_OWNER': 1}
    polls.migrate()
    assert p['multiple'] and p['votes'] == {'U_OWNER': [1]}
    assert 'pick as many as you like' in json.dumps(fresh_bot.updates[-1])
    vote(p, 'U_OWNER', 'Pizza')
    assert p['votes']['U_OWNER'] == [1, 0]


def test_votes_are_public_with_pictures_and_names(poll, fresh_bot):
    _, p = poll
    vote(p, 'U_SALAH', 'Shawarma')
    vote(p, OWNER, 'Shawarma')
    blocks = fresh_bot.updates[-1]['blocks']
    row = next(b for b in blocks if b['type'] == 'context' and b['elements'][0]['type'] == 'image')
    assert [e['image_url'] for e in row['elements'][:-1]] == ['https://img/U_SALAH.png', f'https://img/{OWNER}.png']
    assert row['elements'][-1]['text'] == 'Salah, Sam'
    assert '- Shawarma: 2 (Salah, Sam)' in polls.result(p)


def change(task, **fields):
    agent_sends(task, {'type': 'poll_change', **fields})
    return ledger.items(task)[-1]


def test_the_agent_can_switch_a_poll_to_single_choice_keeping_each_latest_pick(poll, fresh_bot):
    task, p = poll
    p['multiple'] = True
    vote(p, 'U_A', 'Sushi')
    vote(p, 'U_A', 'Pizza')
    vote(p, 'U_B', 'Shawarma')
    it = change(task, poll=p['id'], multiple=False)
    assert not p['multiple'] and p['votes'] == {'U_A': [0], 'U_B': [1]}
    assert '1 person had several picks; their latest was kept' in fresh_bot.text()
    assert it['kind'] == 'poll_change' and it['state'] == 'applied'


def test_the_page_can_change_the_closing_time_and_close_a_poll(poll, fresh_bot):
    _, p = poll
    later = time.time() + 7200
    drop_ask(type='poll', poll=p['id'], closes=later)
    asks.tick()
    assert p['closes'] == later and 'from the hub' in fresh_bot.text()
    drop_ask(type='poll', poll=p['id'], closes=time.time() - 60)
    asks.tick()
    assert p['closes'] == later
    drop_ask(type='poll', poll=p['id'], close=True)
    asks.tick()
    assert not p['open']


def test_polls_are_published_for_the_page_with_their_voters(poll):
    _, p = poll
    vote(p, 'U_SALAH', 'Sushi')
    publish._last = 0.0
    publish.tick()
    row = config.COMP.db.execute('select open, data from polls where id = ?', (p['id'],)).fetchone()
    data = json.loads(row[1])
    assert row[0] == 1 and data['question'] == 'Where?'
    assert data['options'][2] == {
        'label': 'Sushi',
        'votes': 1,
        'voters': [{'name': 'Salah', 'avatar': 'https://img/U_SALAH.png'}],
    }


def test_poll_times_read_as_12_hour_clock():
    two_pm = datetime(2026, 10, 29, 14, 0).timestamp()
    assert say(two_pm, 'day') == 'Thu 2:00 PM'
    assert say(two_pm, 'date') == 'Thu Oct 29, 2:00 PM'


def test_the_owner_can_add_a_vote_for_someone_and_it_says_so(poll, fresh_bot):
    task, p = poll
    change(task, poll=p['id'], vote={'for': 'Ali Example', 'options': ['shawarma']})
    assert p['votes']['U_ALI'] == [1] and p['added_by'] == {'U_ALI': OWNER}
    assert "added Ali's vote for Shawarma" in fresh_bot.text()
    assert 'Ali (added by Sam)' in json.dumps(fresh_bot.updates[-1])
    change(task, poll=p['id'], vote={'for': 'Ali Example', 'remove': True})
    assert 'U_ALI' not in p['votes'] and not p['added_by']


@pytest.mark.parametrize(
    ('who', 'option', 'problem'),
    [
        ('Al', 'Pizza', 'matches 2 people'),
        ('Nobody Here', 'Pizza', 'Nobody in Slack is called'),
        ('Gone Person', 'Pizza', 'Nobody in Slack is called'),
        ('Ali Example', 'Burgers', 'is not one of the options'),
    ],
)
def test_a_vote_for_someone_unclear_is_refused_not_guessed(poll, fresh_bot, who, option, problem):
    task, p = poll
    it = change(task, poll=p['id'], vote={'for': who, 'options': [option]})
    assert p['votes'] == {} and problem in fresh_bot.text()
    assert it['state'] == 'refused' and problem in it['note']


def test_a_later_message_about_a_poll_brings_the_poll_instructions(poll, tagged, monkeypatch):
    _, p = poll
    task, _, _ = tagged
    sent = []
    monkeypatch.setattr(t3, 'send', lambda tid, msg: sent.append(msg) or {'ok': True})
    tasks.follow_up(task, '<@BCOMPANION> add a vote from Ali on Fatto', None, '70.9', 'thread')
    tasks.follow_up(task, '<@BCOMPANION> thanks!', None, '71.0', 'thread')
    assert '"type": "poll_change"' in sent[0] and p['id'] in sent[0]
    assert 'poll_change' not in sent[1]


def test_moving_the_closing_time_updates_the_whole_message(poll, fresh_bot):
    _, p = poll
    later = datetime(2030, 1, 3, 14, 30).timestamp()
    drop_ask(type='poll', poll=p['id'], closes=later, text='Lunch! Links below.')
    asks.tick()
    shown = json.dumps(fresh_bot.updates[-1]['blocks'], ensure_ascii=False)
    assert '**Where?** · closes Thu 2:30 PM' in shown and 'Lunch! Links below.' in shown
    assert shown.count('closes') == 1
