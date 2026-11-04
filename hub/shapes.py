"""JSON shapes the web app understands: server-described buttons and epoch-second times."""

from datetime import datetime


def link(label, href, icon=None, primary=False):
    return {'type': 'link', 'label': label, 'href': href, 'icon': icon, 'primary': primary}


def post(label, url, icon=None, body=None, confirm=None, primary=False):
    return {
        'type': 'post',
        'label': label,
        'url': url,
        'icon': icon,
        'body': body or {},
        'confirm': confirm,
        'primary': primary,
    }


def epoch(value):
    """Epoch seconds from a number or an ISO time; 0 when unreadable."""
    if isinstance(value, int | float):
        return float(value)
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except ValueError:
        return 0.0
