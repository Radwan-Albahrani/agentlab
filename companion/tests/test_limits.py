import json
import time
from datetime import UTC, datetime

import pytest
from bot import limits, machine, publish, state, t3, tasks
from test_turns import task

NOW = datetime(2026, 11, 16, 20, 0, tzinfo=UTC).timestamp()  # 23:00 in Riyadh (UTC+3)
IN_AN_HOUR = time.time() + 3600


def t3_error(reset_at):
    """An \x1brror turn item as T3 writes it for a usage limit."""
    return json.dumps(
        {
            'type': 'error',
            'title': 'Usage limit reached',
            'failure': {
                'class': 'usage_limit',
                'message': 'Claude API rate limit reached. Try again later.',
                'code': 'api_error_429',
                'retryable': True,
                'resetAt': datetime.fromtimestamp(reset_at, UTC).isoformat().replace('+00:00', 'Z'),
            },
        }
    )


def local(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi).timestamp()


@pytest.mark.parametrize(
    ('text', 'resets'),
    [
        ("You've hit your 5-hour limit · resets 1:50am (Asia/Riyadh)", datetime(2026, 11, 16, 22, 50, tzinfo=UTC)),
        ('5-hour limit reached ∙ resets 1am (UTC)', datetime(2026, 11, 17, 1, 0, tzinfo=UTC)),
        (
            'Claude usage limit reached. Your limit will reset at 2pm (Europe/Berlin).',
            datetime(2026, 11, 17, 13, 0, tzinfo=UTC),
        ),
        ('Claude AI usage limit reached|1794783000', 1794783000),
        ('Claude usage limit reached. This turn is paused until the 5-hour limit resets in 1h 31m.', NOW + 5460),
        ("You've hit your usage limit. Upgrade to Pro or try again in 2 hours 5 minutes.", NOW + 7500),
        ('5-hour limit reached', None),
    ],
)
def test_usage_limits_are_read_with_their_reset_time(text, resets):
    expected = resets.timestamp() if isinstance(resets, datetime) else resets
    assert limits.parse(text, NOW) == (True, expected)


def test_a_time_without_a_zone_is_local_and_a_past_time_means_tomorrow():
    now = local(2026, 11, 16, 16, 0)
    assert limits.parse("You've hit your usage limit. Upgrade to Pro or try again at 3:05 PM.", now) == (
        True,
        local(2026, 11, 17, 15, 5),
    )
    assert limits.parse('Usage limit reached, try again at Nov 21st, 2026 4:48 PM.', now)[1] == local(
        2026, 11, 21, 16, 48
    )


@pytest.mark.parametrize(
    'text',
    ['Selected model is at capacity. Please try a different model.', 'exceeded retry limit, last status: 429', ''],
)
def test_passing_errors_are_not_usage_limits(text):
    assert limits.parse(text, NOW) == (False, None)
    assert limits.from_error(json.dumps({'failure': {'class': 'provider_error', 'message': text}}), NOW) == (
        False,
        None,
    )


def test_t3s_error_item_gives_the_class_and_reset():
    reset = datetime(2026, 11, 16, 22, 50, tzinfo=UTC).timestamp()
    assert limits.from_error(t3_error(reset), NOW) == (True, reset)


def turn(status, done='2026-11-16T20:00:00.000Z', running=False):
    return lambda tid, since: {
        'running': running,
        'last_status': status,
        'last_done': done,
        'messages': [],
        'requests': [],
        'workers': [],
        'prs': [],
    }


@pytest.fixture
def limited(monkeypatch, t3_quiet):
    sent = []
    monkeypatch.setattr(t3, 'send', lambda tid, msg: sent.append(msg) or {'ok': True})
    monkeypatch.setattr(t3, 'run_error', lambda tid: t3_error(IN_AN_HOUR))
    monkeypatch.setattr(t3, 'snapshot', turn('failed'))
    return sent


def test_a_usage_limit_pauses_until_t3_resumes_then_finishes_without_a_failure(monkeypatch, limited, fresh_bot):
    t = task()
    tasks.tick(t)
    assert machine.running(t) and t['paused']['resumes_at'] == pytest.approx(IN_AN_HOUR, abs=0.01)
    assert not limited and (t.get('retry') or {}).get('state', 'idle') == 'idle'
    assert 'Paused for the usage limit' in fresh_bot.text() and 'failed' not in fresh_bot.text()
    card = publish.card('k', t)
    assert (card['status'], card['phase'], card['resumes_at']) == ('paused', 'paused', t['paused']['resumes_at'])

    tasks.tick(t)  # still the same failed run: waits
    assert machine.running(t) and not limited

    monkeypatch.setattr(t3, 'snapshot', turn('failed', running=True))  # T3's continuation run
    tasks.tick(t)
    assert 'paused' not in t and publish.card('k', t)['status'] == 'working'

    monkeypatch.setattr(t3, 'run_error', lambda tid: '')
    monkeypatch.setattr(t3, 'snapshot', turn('completed', done='2026-11-16T23:00:00.000Z'))
    t['latest'] = 'The queue is empty.'
    tasks.tick(t)
    assert not machine.running(t) and machine.outcome(t) == 'answered' and not limited


def test_if_t3_does_not_resume_it_says_continue_once_after_the_reset(monkeypatch, limited):
    t = task()
    tasks.tick(t)
    t['paused']['resumes_at'] = state.parse_iso(state.now_iso()) - 14 * 60
    tasks.tick(t)
    assert not limited  # within the 15 minutes T3 gets
    t['paused']['resumes_at'] -= 2 * 60
    tasks.tick(t)
    tasks.tick(t)
    assert limited == ['continue'] and machine.running(t) and t['paused']['nudged']


def test_a_limit_notice_as_the_answer_pauses_too(monkeypatch, limited):
    monkeypatch.setattr(t3, 'run_error', lambda tid: '')
    t = task(latest="You've hit your 5-hour limit · resets 1:50am (Asia/Riyadh)")
    tasks.tick(t)
    assert machine.running(t) and t['paused']['resumes_at']
