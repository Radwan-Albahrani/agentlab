import pytest
from bot import inbox, reviews, routing, tasks
from bot.state import key, state
from conftest import OWNER, set_settings


@pytest.fixture
def channel(monkeypatch):
    set_settings({'requests_channel': 'C_REQ'})
    state.pop('inbox', None)
    calls = []
    monkeypatch.setattr(
        tasks, 'start', lambda ch, tts, ts, text, elsewhere=None, guest=None: calls.append(('task', ts, text, guest))
    )
    monkeypatch.setattr(
        tasks, 'follow_up', lambda task, text, files, ts, by=None: calls.append(('follow', ts, text, by))
    )
    monkeypatch.setattr(
        reviews,
        'from_slack',
        lambda ch, tts, ts, text, by=None, any_words=False: (
            'github.com' in text and not calls.append(('review', ts, by))
        ),
    )
    return calls


def asked(ts='90.1', text='please make the logo bigger', user='U_SALAH', thread=None, tag=True):
    ev = {'channel': 'C_REQ', 'ts': ts, 'user': user, 'text': f'<@BCOMPANION> {text}' if tag else text}
    if thread:
        ev['thread_ts'] = thread
    routing.route(ev, tag)


def card(bot):
    return next(m for m in bot.messages if m['channel'] == 'D_OWNER' and m['thread_ts'] is None)


def last_card(bot):
    return bot.updates[-1]


def test_an_ask_goes_to_the_owner_with_approve_and_decline(fresh_bot, channel):
    asked()
    c = card(fresh_bot)
    assert '**Salah** asked in <#C_REQ>' in c['blocks'][0]['text'] and 'logo bigger' in c['blocks'][0]['text']
    assert [e['action_id'] for e in last_card(fresh_bot)['blocks'][-1]['elements']] == [
        'inbox_approve',
        'inbox_decline',
    ]
    ack = next(m for m in fresh_bot.messages if m['channel'] == 'C_REQ')
    assert ack['thread_ts'] == '90.1' and 'Sent to Sam for approval' in fresh_bot.text()
    assert state['inbox'][key('C_REQ', '90.1')]['status'] == 'pending' and not channel


def test_approved_it_runs_as_their_task_in_the_thread(fresh_bot, channel):
    asked()
    inbox.decide(key('C_REQ', '90.1'), True)
    assert channel == [('task', '90.1', 'please make the logo bigger', 'U_SALAH')]
    assert 'Sam approved this. Starting now.' in fresh_bot.text()
    assert 'actions' not in [b['type'] for b in last_card(fresh_bot)['blocks']]
    inbox.decide(key('C_REQ', '90.1'), False)  # a second click changes nothing
    assert 'declined' not in fresh_bot.text()


def test_an_approved_pr_link_is_a_review_they_follow(fresh_bot, channel):
    asked(text='review https://github.com/example-org/app/pull/5922')
    inbox.decide(key('C_REQ', '90.1'), True)
    assert channel == [('review', '90.1', 'U_SALAH')]


def test_declined_they_are_told_and_nothing_runs(fresh_bot, channel):
    asked()
    inbox.decide(key('C_REQ', '90.1'), False)
    told = [m for m in fresh_bot.messages if m['channel'] == 'C_REQ'][-1]
    assert told['thread_ts'] == '90.1' and told['blocks'][0]['text'] == ':no_entry_sign: Sam declined this request.'
    assert not channel


def test_the_owners_reply_under_the_card_reaches_their_thread(fresh_bot, channel):
    asked()
    c = fresh_bot.messages.index(card(fresh_bot)) + 1
    routing.route(
        {'channel': 'D_OWNER', 'ts': '91.1', 'thread_ts': f'{c}.0', 'user': OWNER, 'text': 'not this week'}, False
    )
    told = fresh_bot.messages[-1]
    assert (told['channel'], told['thread_ts']) == ('C_REQ', '90.1')
    assert told['blocks'][0]['text'] == '**Sam:** not this week'


def test_more_from_them_while_pending_joins_the_ask(fresh_bot, channel):
    asked()
    asked(ts='90.2', text='on mobile too', thread='90.1')
    asked(ts='90.3', text='me too', user='U_ALI', thread='90.1', tag=False)  # someone else's chatter
    asked(ts='90.5', text='and the footer', thread='90.1', tag=False)  # not tagged: just talk
    assert state['inbox'][key('C_REQ', '90.1')]['text'] == 'please make the logo bigger\non mobile too'
    assert '**Salah** added:' in fresh_bot.text() and 'me too' not in fresh_bot.text()
    inbox.decide(key('C_REQ', '90.1'), True)
    assert channel[0][2] == 'please make the logo bigger\non mobile too'


def test_after_approval_their_replies_steer_the_task(fresh_bot, channel):
    asked()
    inbox.decide(key('C_REQ', '90.1'), True)
    state['tasks'][key('C_REQ', '90.1')] = {'channel': 'C_REQ', 'thread_ts': '90.1', 'guest': 'U_SALAH'}
    asked(ts='90.4', text='make it green too', thread='90.1')
    assert channel[-1] == ('follow', '90.4', '<@BCOMPANION> make it green too', 'U_SALAH')  # follow_up drops the tag


@pytest.mark.parametrize('settings', [{}, {'requests_channel': 'C_REQ', 'mode': 'owner'}])
def test_nothing_is_taken_without_the_channel_or_in_dry_run(fresh_bot, channel, settings):
    set_settings(settings)
    asked()
    assert not state.get('inbox') and not any(m['channel'] == 'D_OWNER' for m in fresh_bot.messages)


def test_only_the_owner_can_press_the_buttons(fresh_bot, channel):
    asked()
    k = key('C_REQ', '90.1')
    press = inbox._decide_action(True)
    press(lambda: None, {'user': {'id': 'U_SALAH'}, 'actions': [{'value': k}]})
    assert state['inbox'][k]['status'] == 'pending'
    press(lambda: None, {'user': {'id': OWNER}, 'actions': [{'value': k}]})
    assert state['inbox'][k]['status'] == 'approved'


def test_untagged_talk_in_the_channel_is_left_alone(fresh_bot, channel):
    asked(tag=False)
    asked(ts='92.1', text='what do you all think?', user='U_ALI', tag=False)
    assert not state.get('inbox') and not fresh_bot.messages and not channel


def test_after_approval_untagged_replies_are_just_talk(fresh_bot, channel):
    asked()
    inbox.decide(key('C_REQ', '90.1'), True)
    state['tasks'][key('C_REQ', '90.1')] = {'channel': 'C_REQ', 'thread_ts': '90.1', 'guest': 'U_SALAH'}
    asked(ts='90.6', text='nice, thanks', thread='90.1', tag=False)
    assert channel[-1][0] == 'task'
