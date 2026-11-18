"""Times for people: one module, named forms, a 12-hour clock with AM/PM everywhere."""

import os
import re
import time
from datetime import datetime

import pytest
from bot import prompts, when

BOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bot')


@pytest.mark.parametrize(
    ('form', 'shown'),
    [
        ('time', '9:05 AM'),
        ('day', 'Thu 9:05 AM'),
        ('date', 'Thu Oct 29, 9:05 AM'),
        ('stamp', 'Oct 29, 9:05 AM'),
    ],
)
def test_each_form_is_twelve_hour_with_no_leading_zeros(form, shown):
    assert when.say(datetime(2026, 10, 29, 9, 5).timestamp(), form) == shown


def test_noon_and_midnight_read_as_twelve():
    assert when.say(datetime(2026, 10, 29, 12, 0).timestamp()) == '12:00 PM'
    assert when.say(datetime(2026, 10, 29, 0, 30).timestamp()) == '12:30 AM'
    assert when.say(datetime(2026, 11, 7, 16, 45).timestamp(), 'stamp') == 'Nov 7, 4:45 PM'


def test_near_names_the_day_only_when_it_is_more_than_a_day_away():
    soon = time.time() + 3600
    assert when.say(soon, 'near') == when.say(soon, 'time')
    later = time.time() + 3 * 86400
    assert when.say(later, 'near') == when.say(later, 'day')


def test_no_time_for_people_is_written_on_a_24_hour_clock():
    """Only ISO stamps (for T3 and the agent to compute with) and the log may use %H; anything else goes via when."""
    offenders = []
    for name in sorted(os.listdir(BOT)):
        if not name.endswith('.py') or name == 'when.py':
            continue
        with open(os.path.join(BOT, name)) as f:
            for n, line in enumerate(f, 1):
                for fmt in re.findall(r"strftime\(\s*f?(['\"])(.*?)\1", line):
                    pattern = fmt[1]
                    if ('%H' in pattern or '%I' in pattern) and 'T%H' not in pattern and name != 'config.py':
                        offenders.append(f'{name}:{n}: {pattern}')
    assert offenders == []


def test_the_agent_is_told_to_write_times_with_am_and_pm():
    p = prompts.task('x', 'Sam', 'a DM with you', [], [], 'f', '', [], '')
    assert when.RULE in p and when.RULE in prompts.side_answer('status?', 'record')
    guest = prompts.task('x', 'Sam', 'a DM with you', [], [], 'f', '', [], '', 'Salah')
    assert when.RULE in guest and when.RULE in prompts.errand('Ali', 'asked you', 'Sam', 'x', [], [], 'f')
