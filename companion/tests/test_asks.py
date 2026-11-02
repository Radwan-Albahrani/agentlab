"""Asks from the hub: an ask starts the agent in the owner's DM, its post.json is previewed and posted only on
the owner's tap (unless he said not to ask), and polls collect votes, close on time and announce the winner."""

import json
import os
import time
from datetime import datetime, timedelta

import pytest
from bot import asks, config, errands, outbox, polls, posts, projects, publish, state, t3, tasks
from bot.text import clock
from conftest import OWNER

IN_AN_HOUR = (datetime.now().astimezone() + timedelta(hours=1)).isoformat()


def drop_ask(**ask):
    with open(os.path.join(config.COMP.asks_dir, f'{time.time_ns()}.json'), 'w') as f:
        json.dump(ask, f)


@pytest.fixture
def started(t3_quiet, monkeypatch):
    """Start an ask through the page's folder; returns (task, its outbox, what the agent was told)."""
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


def write_post(box, post):
    with open(os.path.join(box, 'post.json'), 'w') as f:
        json.dump(post, f)


def press(action, task, user=OWNER):
    handler = {'send': lambda t, k: posts.decide(t, k, True), 'skip': lambda t, k: posts.decide(t, k, False)}[action]
    k = state.key(task['channel'], task['thread_ts'])
    body = {'user': {'id': user}, 'actions': [{'value': k}], 'channel': {'id': 'D_OWNER'}, 'message': {'ts': 'x'}}
    errands.owner_action(handler)(lambda: None, body)


def channel_posts(bot, channel):
    return [m for m in bot.messages if m['channel'] == channel]


def test_an_ask_is_taken_once_and_starts_the_agent_in_the_owners_dm(started, fresh_bot):
    task, _, told = started(text='Announce the deploy freeze on Thursday', channel='C_TECH', review=True)
    assert task['channel'] == 'D_OWNER' and task['thread'] == 'T_ASK'
    assert 'deploy freeze' in told and 'C_TECH' in told and '#ask-tech' in told and 'post.json' in told
    assert os.listdir(config.COMP.asks_dir) == []  # taken: it never runs twice
    assert 'From the hub' in fresh_bot.text()


def test_a_post_waits_for_the_owners_tap_and_only_the_owner_can_give_it(started, fresh_bot):
    task, box, _ = started(text='Announce the freeze', channel='C_TECH', review=True)
    write_post(box, {'channel': 'C_TECH', 'text': 'Deploy freeze on Thursday.'})
    outbox.tick(task)
    assert channel_posts(fresh_bot, 'C_TECH') == []
    assert ['post_send', 'post_skip'] in fresh_bot.actions()
    assert publish.card('k', task)['waiting'] == 'post'
    press('send', task, user='U_SALAH')
    assert channel_posts(fresh_bot, 'C_TECH') == []
    press('send', task)
    assert channel_posts(fresh_bot, 'C_TECH')[0]['text'] == 'Deploy freeze on Thursday.'


def test_dont_post_posts_nothing(started, fresh_bot):
    task, box, _ = started(text='x', channel='C_TECH', review=True)
    write_post(box, {'channel': 'C_TECH', 'text': 'Hello'})
    outbox.tick(task)
    press('skip', task)
    assert channel_posts(fresh_bot, 'C_TECH') == []


def test_without_review_it_goes_out_at_once(started, fresh_bot):
    task, box, _ = started(text='x', channel='C_TECH', review=False)
    write_post(box, {'channel': '#ask-tech', 'text': 'Hello all'})  # a channel name works too
    outbox.tick(task)
    assert channel_posts(fresh_bot, 'C_TECH')[0]['text'] == 'Hello all'


def test_a_channel_companion_is_not_in_is_refused_with_how_to_fix_it(started, fresh_bot):
    task, box, _ = started(text='x', channel='', review=False)
    write_post(box, {'channel': 'C_ELSEWHERE', 'text': 'Hello'})
    outbox.tick(task)
    assert channel_posts(fresh_bot, 'C_ELSEWHERE') == []
    assert '/invite @Companion' in fresh_bot.text()


def test_a_revised_post_retires_the_older_preview(started, fresh_bot):
    task, box, _ = started(text='x', channel='C_TECH', review=True)
    write_post(box, {'channel': 'C_TECH', 'text': 'First'})
    outbox.tick(task)
    write_post(box, {'channel': 'C_TECH', 'text': 'Second'})
    outbox.tick(task)
    assert 'Replaced by the version below' in json.dumps(fresh_bot.updates)
    press('send', task)
    assert [m['text'] for m in channel_posts(fresh_bot, 'C_TECH')] == ['Second']


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
    task, box, _ = started(text='Lunch poll', channel='C_RANDOM', review=False)
    write_post(
        box,
        {
            'channel': 'C_RANDOM',
            'text': 'Team lunch on Thursday!',
            'poll': {'question': 'Where?', 'options': ['Pizza', 'Shawarma', 'Sushi'], 'closes': IN_AN_HOUR},
        },
    )
    outbox.tick(task)
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
    vote(p, 'U_A', 'Sushi')  # changes their vote
    assert polls.counts(p) == [1, 0, 1]
    vote(p, 'U_B', 'Pizza')  # the same choice again takes it back
    assert polls.counts(p) == [0, 0, 1]
    assert '1 vote' in json.dumps(fresh_bot.updates[-1])
    assert publish.card('k', task)['status'] == 'working' and 'Poll open' in publish.card('k', task)['outcome']


def test_the_poll_closes_on_time_and_announces_the_winner(poll, fresh_bot):
    task, p = poll
    vote(p, 'U_A', 'Shawarma')
    vote(p, 'U_B', 'Shawarma')
    vote(p, 'U_C', 'Pizza')
    polls.tick()
    assert p['open']  # not yet
    p['closes'] = time.time() - 1
    polls.tick()
    assert not p['open']
    announce = channel_posts(fresh_bot, 'C_RANDOM')[-1]
    assert announce['thread_ts'] == p['ts'] and announce['reply_broadcast']
    assert '**Shawarma** wins with 2 of 3 votes' in json.dumps(announce['blocks'])
    vote(p, 'U_D', 'Pizza')  # too late
    assert polls.counts(p) == [1, 2, 0]
    task['active'] = False  # the agent's turn ended long ago
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


# ---------------------------------------------------------------- tagged in a channel
@pytest.fixture
def tagged(t3_quiet, monkeypatch):
    """The owner tagged the companion under the restaurant list in #random: "make a poll, ends at 2pm"."""
    told = []
    monkeypatch.setattr(t3, 'start_thread', lambda project, title, message: told.append(message) or ('T_TAG', ''))
    monkeypatch.setattr(projects, 'pick', lambda ask, convo, chan: ('/workspace/x', 'test'))
    tasks.start('C_RANDOM', '70.1', '70.2', '<@BCOMPANION> make a poll ends at 2pm')
    task = state.state['tasks'][state.key('C_RANDOM', '70.1')]
    box = os.path.join(outbox.OUTBOX, task['outbox'])
    os.makedirs(box, exist_ok=True)
    return task, box, told[0]


LUNCH = {
    'text': 'Lunch on Thursday: pick a place!\n- Peradiz (Indian): https://maps.app.goo.gl/kRDMYyC9x8qAdJpYA',
    'poll': {'question': 'Where do we eat?', 'options': ['Peradiz (Indian)', 'Fatto (Italian)'], 'closes': IN_AN_HOUR},
}


def test_the_agent_is_told_it_can_post_here_without_a_preview(tagged):
    _, _, told = tagged
    assert 'post.json' in told and 'C_RANDOM' in told and 'right away' in told


def test_a_poll_asked_for_in_a_channel_is_a_new_message_there_at_once(tagged, fresh_bot):
    task, box, _ = tagged
    write_post(box, LUNCH)  # no channel: the one he asked in
    outbox.tick(task)
    (p,) = state.state['polls'].values()
    poll_msg = next(m for m in fresh_bot.messages if m['channel'] == 'C_RANDOM' and m.get('text') == 'Where do we eat?')
    assert 'thread_ts' not in poll_msg  # its own message, not a thread reply
    assert 'post_send' not in json.dumps(fresh_bot.actions())  # no preview: he asked right there
    in_thread = [m for m in fresh_bot.messages if m['channel'] == 'C_RANDOM' and m.get('thread_ts') == '70.1']
    assert 'Poll posted in #' in json.dumps(in_thread)
    owner_dm = [m for m in fresh_bot.messages if m['channel'] == 'D_OWNER']
    assert ['poll_close'] in [
        [e['action_id'] for b in m['blocks'] if b['type'] == 'actions' for e in b['elements']] for m in owner_dm
    ]
    assert p['channel'] == 'C_RANDOM'


def test_once_posted_the_agents_wrap_up_stays_out_of_the_thread(tagged, fresh_bot):
    task, box, _ = tagged
    write_post(box, LUNCH)
    outbox.tick(task)
    before = len(fresh_bot.messages)
    task['latest'] = 'I prepared the lunch poll.'
    tasks._finish_turn(task, {'last_status': 'completed', 'last_done': None})
    assert len(fresh_bot.messages) == before  # nothing new posted
    assert task['outcome'] == 'posted'


def test_a_post_for_another_channel_still_asks_first(tagged, fresh_bot):
    task, box, _ = tagged
    write_post(box, {'channel': 'C_TECH', 'text': 'Hello tech'})
    outbox.tick(task)
    assert channel_posts(fresh_bot, 'C_TECH') == []
    assert ['post_send', 'post_skip'] in fresh_bot.actions()


# ---------------------------------------------------------------- straight to people
def test_a_message_by_dm_is_previewed_even_when_asked_in_the_channel(tagged, fresh_bot):
    task, box, told = tagged
    assert '"to"' in told
    write_post(box, {'to': ['Ali', 'Ali Khan'], 'text': 'Sam asked me to let you know: lunch at 2.'})
    outbox.tick(task)
    assert channel_posts(fresh_bot, 'D_U_ALI') == []
    assert '<@U_ALI>, <@U_ALI2> by DM' in fresh_bot.text()
    press('send', task)
    assert channel_posts(fresh_bot, 'D_U_ALI')[0]['text'].startswith('Sam asked me')
    assert channel_posts(fresh_bot, 'D_U_ALI2')
    assert 'Message sent to Ali, Ali Khan by DM' in fresh_bot.text()


def test_an_unclear_person_is_refused_with_why(tagged, fresh_bot):
    task, box, _ = tagged
    write_post(box, {'to': 'Al', 'text': 'Hi'})
    outbox.tick(task)
    assert 'matches 2 people' in fresh_bot.text()
    assert 'post_send' not in json.dumps(fresh_bot.actions())


# ---------------------------------------------------------------- multiple choice
def test_multiple_choice_lets_people_pick_several_and_take_one_back(started, fresh_bot):
    task, box, _ = started(text='x', channel='C_RANDOM', review=False)
    write_post(
        box,
        {
            'channel': 'C_RANDOM',
            'text': '',
            'poll': {
                'question': 'Which days?',
                'options': ['Mon', 'Tue', 'Wed'],
                'closes': IN_AN_HOUR,
                'multiple': True,
            },
        },
    )
    outbox.tick(task)
    (p,) = state.state['polls'].values()
    vote(p, 'U_A', 'Mon')
    vote(p, 'U_A', 'Wed')
    vote(p, 'U_B', 'Wed')
    assert polls.counts(p) == [1, 0, 2] and polls.voters(p) == 2
    vote(p, 'U_A', 'Mon')  # pressed again: only that one is taken back
    assert p['votes']['U_A'] == [2]
    assert 'pick as many as you like' in json.dumps(fresh_bot.updates[-1])
    assert '**Wed** wins: 2 of the 2 people who voted picked it' in polls.result(p)


def test_polls_from_before_become_multiple_choice_and_keep_their_votes(poll, fresh_bot):
    _, p = poll
    p.pop('multiple')
    p['votes'] = {'U_OWNER': 1}  # the old shape: one index per person
    polls.migrate()
    assert p['multiple'] and p['votes'] == {'U_OWNER': [1]}
    assert 'pick as many as you like' in json.dumps(fresh_bot.updates[-1])  # its message was redrawn
    vote(p, 'U_OWNER', 'Pizza')
    assert p['votes']['U_OWNER'] == [1, 0]  # in the order picked


def test_votes_are_public_with_pictures_and_names(poll, fresh_bot):
    _, p = poll
    vote(p, 'U_SALAH', 'Shawarma')
    vote(p, OWNER, 'Shawarma')
    blocks = fresh_bot.updates[-1]['blocks']
    row = next(b for b in blocks if b['type'] == 'context' and b['elements'][0]['type'] == 'image')
    assert [e['image_url'] for e in row['elements'][:-1]] == ['https://img/U_SALAH.png', f'https://img/{OWNER}.png']
    assert row['elements'][-1]['text'] == 'Salah, Sam'
    assert '- Shawarma: 2 (Salah, Sam)' in polls.result(p)


# ---------------------------------------------------------------- changing a poll
def drop_change(box, change):
    with open(os.path.join(box, 'poll-change.json'), 'w') as f:
        json.dump(change, f)


def test_the_agent_can_switch_a_poll_to_single_choice_keeping_each_latest_pick(poll, fresh_bot):
    task, p = poll
    p['multiple'] = True
    vote(p, 'U_A', 'Sushi')
    vote(p, 'U_A', 'Pizza')  # picked last
    vote(p, 'U_B', 'Shawarma')
    drop_change(os.path.join(outbox.OUTBOX, task['outbox']), {'poll': p['id'], 'multiple': False})
    outbox.tick(task)
    assert not p['multiple'] and p['votes'] == {'U_A': [0], 'U_B': [1]}
    assert '1 person had several picks; their latest was kept' in fresh_bot.text()
    assert task['posted']  # the companion's line is the answer; the agent's wrap-up stays out


def test_the_page_can_change_the_closing_time_and_close_a_poll(poll, fresh_bot):
    _, p = poll
    later = time.time() + 7200
    drop_ask(type='poll', poll=p['id'], closes=later)
    asks.tick()
    assert p['closes'] == later and 'from the hub' in fresh_bot.text()
    drop_ask(type='poll', poll=p['id'], closes=time.time() - 60)  # the past: refused, nothing changes
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
    assert clock(two_pm) == 'Thu 2:00 PM'
    assert clock(two_pm, date=True) == 'Thu Oct 29, 2:00 PM'


# ---------------------------------------------------------------- voting for someone
def test_the_owner_can_add_a_vote_for_someone_and_it_says_so(poll, fresh_bot):
    task, p = poll
    box = os.path.join(outbox.OUTBOX, task['outbox'])
    drop_change(box, {'poll': p['id'], 'vote': {'for': 'Ali Example', 'options': ['shawarma']}})
    outbox.tick(task)
    assert p['votes']['U_ALI'] == [1] and p['added_by'] == {'U_ALI': OWNER}
    assert "added Ali's vote for Shawarma" in fresh_bot.text()  # Slack's display name for him
    assert 'Ali (added by Sam)' in json.dumps(fresh_bot.updates[-1])  # public: shown as added
    drop_change(box, {'poll': p['id'], 'vote': {'for': 'Ali Example', 'remove': True}})
    outbox.tick(task)
    assert 'U_ALI' not in p['votes'] and not p['added_by']


@pytest.mark.parametrize(
    ('who', 'option', 'problem'),
    [
        ('Al', 'Pizza', 'matches 2 people'),  # Ali Example and Ali Khan
        ('Nobody Here', 'Pizza', 'Nobody in Slack is called'),
        ('Gone Person', 'Pizza', 'Nobody in Slack is called'),  # deactivated
        ('Ali Example', 'Burgers', 'is not one of the options'),
    ],
)
def test_a_vote_for_someone_unclear_is_refused_not_guessed(poll, fresh_bot, who, option, problem):
    task, p = poll
    drop_change(
        os.path.join(outbox.OUTBOX, task['outbox']), {'poll': p['id'], 'vote': {'for': who, 'options': [option]}}
    )
    outbox.tick(task)
    assert p['votes'] == {} and problem in fresh_bot.text()


def test_a_later_message_about_a_poll_brings_the_poll_instructions(poll, tagged, monkeypatch):
    _, p = poll
    task, _, _ = tagged
    sent = []
    monkeypatch.setattr(t3, 'send', lambda tid, msg: sent.append(msg) or {'ok': True})
    tasks.follow_up(task, '<@BCOMPANION> add a vote from Ali on Fatto', None, '70.9')
    tasks.follow_up(task, '<@BCOMPANION> thanks!', None, '71.0')
    assert 'poll-change.json' in sent[0] and p['id'] in sent[0]
    assert 'poll-change.json' not in sent[1]


def test_moving_the_closing_time_updates_the_whole_message(poll, fresh_bot):
    _, p = poll
    later = datetime(2030, 1, 3, 14, 30).timestamp()  # a Thursday
    drop_ask(type='poll', poll=p['id'], closes=later, text='Lunch! Links below.')
    asks.tick()
    shown = json.dumps(fresh_bot.updates[-1]['blocks'], ensure_ascii=False)
    assert '**Where?** · closes Thu 2:30 PM' in shown and 'Lunch! Links below.' in shown
    assert shown.count('closes') == 1  # only the companion's own line says when
