"""What the page shows: each item is 'show', 'present' (hidden while presenting) or 'hide'; hidden things are never sent."""

import json
import os
from typing import Any

import cluster

FILE = os.path.join(os.environ.get('NOTIFY_DATA', '/data'), 'display.json')
INFRA = 'present'


def items() -> list[tuple[str, str, str, str]]:
    """[(group, key, label, default)] for everything that can be hidden."""
    out = [
        ('Overview', 'overview.tiles', 'Key numbers', 'show'),
        ('Overview', 'overview.needs', 'Needs you', 'show'),
        ('Overview', 'overview.now', 'What the agents are doing now (chat titles)', 'show'),
        ('Overview', 'overview.activity', 'Recent activity', 'show'),
        ('Overview', 'overview.stacks', 'Stacks', INFRA),
        ('Agents', 'page.agents', 'All agents page', 'show'),
    ]
    out += [('Agents', f'profile.{p}', f'{p} agent', 'show') for p in cluster.ids()]
    out += [
        ('Agents', 'agent.resources', 'Memory and heavy jobs', INFRA),
        ('Agents', 'agent.containers', 'Containers on agent pages', INFRA),
        ('Agents', 'agent.pairing', 'Pair a device', INFRA),
        ('Agents', 'agent.env', 'Environment variables', INFRA),
    ]
    out += [
        ('Companions', f'companion.{n}', f'{cluster.display_name(n)} ({p})', 'show')
        for n, p in cluster.companions().items()
    ]
    out += [
        ('Companions', 'companion.ask', 'Ask box (post or poll in a channel)', 'show'),
        ('Companions', 'companion.polls', 'Polls and who voted', 'show'),
        ('Companions', 'companion.pulls', 'Pull requests and reviews', 'show'),
        ('Companions', 'companion.delivered', 'Who received what', 'show'),
        ('Companions', 'companion.settings', 'Companion settings', INFRA),
    ]
    out += [
        ('System', f'page.{k}', label, INFRA)
        for k, label in (
            ('manage', 'Manage agents'),
            ('services', 'Services'),
            ('config', 'Configs'),
            ('storage', 'Storage'),
            ('secrets', 'Secrets'),
            ('notifications', 'Notifications'),
        )
    ]
    return out


def load() -> dict[str, Any]:
    try:
        with open(FILE) as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {}
    return {'presenting': bool(s.get('presenting')), 'items': s.get('items') or {}}


def save(s: dict[str, Any]) -> None:
    with open(FILE + '.tmp', 'w') as f:
        json.dump(s, f, indent=1)
    os.replace(FILE + '.tmp', FILE)


def mode(key: str, s: dict[str, Any] | None = None) -> str:
    s = s or load()
    default = next((d for _, k, _, d in items() if k == key), 'show')
    return s['items'].get(key, default)


def visible(key: str, s: dict[str, Any] | None = None) -> bool:
    s = s or load()
    if key == 'display':  # always reachable by its address
        return True
    m = mode(key, s)
    return m == 'show' or (m == 'present' and not s['presenting'])


def set_mode(key: str, value: object) -> None:
    if value not in ('show', 'present', 'hide') or key not in {k for _, k, _, _ in items()}:
        raise ValueError('Unknown setting.')
    s = load()
    s['items'][key] = value
    save(s)


def set_presenting(on: object) -> None:
    s = load()
    s['presenting'] = bool(on)
    save(s)
