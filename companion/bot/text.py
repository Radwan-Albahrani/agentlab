"""Small text helpers with no Slack or T3 access (times for people: when.py)."""

import re


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
    """':seedling: thinking' -> 'thinking'."""
    return re.sub(r':[a-z0-9_+-]+:\s*', '', text or '')


def without_mention(text, addressed):
    """Drop a leading @-mention of the companion (an id in `addressed`); any other mention is part of the ask."""
    m = re.match(r'\s*<@([A-Z0-9]+)>\s*', text or '')
    return (text or '')[m.end() :] if m and m.group(1) in addressed else text or ''


def to_slack(md, limit=3500):
    """Agent markdown -> Slack mrkdwn."""
    t = md or ''
    t = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)', r'<\2|\1>', t)
    t = re.sub(r'^#{1,6}\s*(.+)$', r'*\1*', t, flags=re.M)
    t = re.sub(r'\*\*(.+?)\*\*', r'*\1*', t)
    t = re.sub(r'^(\s*)[-*]\s+', r'\1• ', t, flags=re.M)
    return t if len(t) <= limit else t[:limit].rsplit('\n', 1)[0] + '\n…_(the rest is in the T3 chat)_'
