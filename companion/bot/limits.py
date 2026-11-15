"""Usage limits (Claude's 5-hour or weekly, Codex's): told apart from passing errors, with the time they reset."""

import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

LIMIT = re.compile(
    r'usage limit|limit reached|hit your (?:[\w-]+ )?limit|\b(?:5|five)-hour limit|weekly limit|limit (?:will )?resets?',
    re.I,
)
EPOCH = re.compile(r'\|\s*(\d{10})\b')  # "Claude AI usage limit reached|1794783000"
IN = re.compile(
    r'\b(?:resets?|try again)\s+in\s+((?:\d+\s*(?:days?|d|hours?|hrs?|h|minutes?|mins?|m)\b(?:\s|,|and)*)+)', re.I
)
MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
AT = re.compile(
    r'\b(?:resets?|reset at|try again at|available (?:again )?at|until)\s+(?:at\s+|on\s+)?'
    r'(?:(?P<month>' + '|'.join(MONTHS) + r')[a-z]*\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?,?\s*(?:(?P<year>\d{4}),?\s*)?'
    r'(?:at\s+)?)?(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ampm>[ap]\.?\s?m\.?)?(?![\w:])'
    r'(?:\s*\(?(?P<zone>[A-Za-z]+/[A-Za-z_]+(?:/[A-Za-z_]+)?|UTC|GMT)\)?)?',
    re.I,
)


def parse(text, now=None):
    """(True, reset epoch or None) when the text tells of a usage limit, else (False, None)."""
    text = str(text or '')
    if not LIMIT.search(text):
        return False, None
    return True, resets_at(text, now)


def from_error(payload, now=None):
    """The same from a T3 `error` turn item (JSON): failure.class 'usage_limit' with failure.resetAt, else its text."""
    try:
        item = json.loads(payload) if payload else {}
    except ValueError:
        return parse(payload, now)
    failure = item.get('failure') if isinstance(item, dict) else None
    if isinstance(failure, dict) and failure.get('class') == 'usage_limit':
        return True, _iso(failure.get('resetAt')) or resets_at(failure.get('message'), now)
    if not isinstance(item, dict):
        return False, None
    return parse(
        ' · '.join(str(x) for x in (item.get('title'), (failure or {}).get('message'), item.get('message')) if x), now
    )


def resets_at(text, now=None):
    """When the limit resets, read leniently from the text; a time without a zone is in local (cluster) time."""
    now = now if now is not None else datetime.now().timestamp()
    text = str(text or '')
    m = EPOCH.search(text)
    if m:
        return float(m.group(1))
    m = IN.search(text)
    if m:
        return now + _span(m.group(1))
    for m in AT.finditer(text):
        if m.group('ampm') or m.group('m'):  # a bare number ("resets 5") is no time
            at = _clock(m, now)
            if at is not None:
                return at
    return None


def _span(text):
    units = {'d': 86400, 'h': 3600, 'm': 60}
    return sum(int(n) * units[u[0].lower()] for n, u in re.findall(r'(\d+)\s*([a-z]+)', text, re.I))


def _zone(name):
    if not name:
        return None
    try:
        return ZoneInfo('UTC' if name.upper() == 'GMT' else name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _clock(m, now):
    h, mins = int(m.group('h')), int(m.group('m') or 0)
    ampm = (m.group('ampm') or '').lower()[:1]
    if ampm:
        if not 1 <= h <= 12:
            return None
        h = h % 12 + (12 if ampm == 'p' else 0)
    if h > 23 or mins > 59:
        return None
    zone = _zone(m.group('zone'))
    base = datetime.fromtimestamp(now, zone) if zone else datetime.fromtimestamp(now).astimezone()
    try:
        if m.group('month'):
            month = MONTHS.index(m.group('month')[:3].lower()) + 1
            year = int(m.group('year') or base.year)
            at = base.replace(
                year=year, month=month, day=int(m.group('day')), hour=h, minute=mins, second=0, microsecond=0
            )
            if not m.group('year') and at.timestamp() < now - 86400:
                at = at.replace(year=year + 1)
            return at.timestamp()
        at = base.replace(hour=h, minute=mins, second=0, microsecond=0)
    except ValueError:
        return None
    if at.timestamp() < now - 300:  # a time already past today means tomorrow
        at += timedelta(days=1)
    return at.timestamp()


def _iso(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp() if value else None
    except ValueError:
        return None
