"""Who the current request is for and what they may see: their own agents and companions; admins see everything."""

import contextvars
from dataclasses import dataclass

import cluster

ADMIN_ONLY = {'page.services', 'page.config', 'page.secrets', 'page.notifications', 'storage.manage', 'display'}


@dataclass(frozen=True)
class Viewer:
    email: str
    admin: bool
    agents: frozenset

    def sees_agent(self, agent_id):
        return self.admin or agent_id in self.agents

    def sees_companion(self, name):
        owner = cluster.companions().get(name)
        return owner is not None and self.sees_agent(owner)

    def sees_person(self, email):
        return self.admin or (email or '').lower() == self.email

    def sees(self, key):
        """Whether a display key ('page.services', 'profile.<id>', 'companion.<name>', ...) is in scope."""
        if key in ADMIN_ONLY:
            return self.admin
        kind, _, name = key.partition('.')
        if kind == 'profile' and name:
            return self.sees_agent(name)
        if kind == 'companion' and name in cluster.companions():
            return self.sees_companion(name)
        if kind == 'person':
            return self.sees_person(name)
        return True


ADMIN = Viewer('local', True, frozenset())
_current = contextvars.ContextVar('viewer', default=ADMIN)  # outside a request (watcher, tests): everything


def of(email, admin=None):
    email = (email or '').strip().lower()
    admins = {a.lower() for a in cluster.auth().get('admins') or []}
    owned = frozenset(a['id'] for a in cluster.agents().values() if (a.get('owner') or '').lower() == email)
    return Viewer(email, email in admins if admin is None else admin, owned)


def use(viewer):
    _current.set(viewer)


def current():
    return _current.get()
