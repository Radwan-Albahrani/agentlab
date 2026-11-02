"""Small text helpers with no Slack or T3 access."""

import re
from datetime import datetime


def first_sentence(text, limit=180):
    t = re.sub(r'\s+', ' ', re.sub(r'[*_`#>]', '', text or '')).strip()
    m = re.match(r'(.+?[.!?])(\s|$)', t)
    t = m.group(1) if m else t
    return t if len(t) <= limit else t[: limit - 1].rsplit(' ', 1)[0] + '…'


def mins(sec):
    return f'{sec / 60:.0f} min' if sec >= 90 else f'{max(sec, 1):.0f} s'


def quote(text):
    return '> ' + '\n> '.join(str(text).splitlines())


def no_emoji(text):
    """':seedling: thinking' -> 'thinking': notification and fallback text shouldn't show emoji codes."""
    return re.sub(r':[a-z0-9_+-]+:\s*', '', text or '')


def without_mention(text):
    """Drop the leading @-mention that addressed the companion."""
    return re.sub(r'<@[A-Z0-9]+>\s*', '', text or '', count=1)


def to_slack(md, limit=3500):
    """Agent markdown -> Slack mrkdwn (for places that can't take a markdown block)."""
    t = md or ''
    t = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)', r'<\2|\1>', t)
    t = re.sub(r'^#{1,6}\s*(.+)$', r'*\1*', t, flags=re.M)
    t = re.sub(r'\*\*(.+?)\*\*', r'*\1*', t)
    t = re.sub(r'^(\s*)[-*]\s+', r'\1• ', t, flags=re.M)
    return t if len(t) <= limit else t[:limit].rsplit('\n', 1)[0] + '\n…_(the rest is in the T3 chat)_'


def clock(ts, date=False):
    """A time people read in Slack, 12-hour: "Thu 2:00 PM", or "Thu Oct 30, 2:00 PM" with the date."""
    d = datetime.fromtimestamp(ts)
    return d.strftime('%a %b %d, ' if date else '%a ') + d.strftime('%I:%M %p').lstrip('0')
