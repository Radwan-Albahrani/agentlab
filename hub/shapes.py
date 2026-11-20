"""JSON shapes the web app understands: server-described buttons and epoch-second times."""

from datetime import datetime
from typing import Any


def link(label: str, href: str, icon: str | None = None, primary: bool = False) -> dict[str, Any]:
    return {'type': 'link', 'label': label, 'href': href, 'icon': icon, 'primary': primary}


def post(
    label: str,
    url: str,
    icon: str | None = None,
    body: dict[str, Any] | None = None,
    confirm: str | None = None,
    primary: bool = False,
) -> dict[str, Any]:
    return {
        'type': 'post',
        'label': label,
        'url': url,
        'icon': icon,
        'body': body or {},
        'confirm': confirm,
        'primary': primary,
    }


def epoch(value: object) -> float:
    """Epoch seconds from a number or an ISO time; 0 when unreadable."""
    if isinstance(value, int | float):
        return float(value)
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except ValueError:
        return 0.0
