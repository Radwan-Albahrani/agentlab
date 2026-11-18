"""Every time the companion shows people, in one place: a 12-hour clock with AM/PM, never 24-hour.

FORMS names each shape a time can take; say() is the only way to write one. Machine times (T3's ISO stamps, the log,
ISO times handed to the agent to compute with) are not for people and stay ISO.

  time   1:50 PM
  day    Thu 1:50 PM
  date   Thu Oct 30, 1:50 PM
  stamp  Nov 7, 4:45 PM            (lines of a Slack transcript)
  near   1:50 PM within a day of now, else Thu 1:50 PM"""

import time
from datetime import datetime

FORMS = {
    'time': '{h}:%M %p',
    'day': '%a {h}:%M %p',
    'date': '%a %b {d}, {h}:%M %p',
    'stamp': '%b {d}, {h}:%M %p',
}
RULE = 'Write every time for people on a 12-hour clock with AM or PM (2:30 PM), never 24-hour (14:30).'


def say(ts=None, form='time'):
    """`ts` (epoch; None: now) in the named form."""
    ts = time.time() if ts is None else float(ts)
    if form == 'near':
        form = 'time' if abs(ts - time.time()) <= 86400 else 'day'
    d = datetime.fromtimestamp(ts)
    return d.strftime(FORMS[form].format(h=d.hour % 12 or 12, d=d.day))
