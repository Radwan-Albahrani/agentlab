"""Who the current request is for, and what they may see. The hub serves everyone with an agent: people see the
agents they own (one person may own several) and those agents' companions; admins see everything plus the cluster
screens. Set once per request by hub.py (each request runs in its own thread, so a context variable keeps requests
apart); every screen and route asks here."""

import contextvars
from dataclasses import dataclass

import cluster

# Cluster-wide screens and switches: admins only. (Storage is open to everyone, scoped to their own disk.)
ADMIN_ONLY = {'page.services', 'page.config', 'page.secrets', 'page.notifications', 'storage.manage', 'display'}


@dataclass(frozen=True)
class Viewer:
    email: str
    admin: bool
    agents: frozenset  # the agents this person owns

    def sees_agent(self, agent_id):
        return self.admin or agent_id in self.agents

    def sees_companion(self, name):
        owner = cluster.companions().get(name)
        return owner is not None and self.sees_agent(owner)

    def sees_person(self, email):
        return self.admin or (email or '').lower() == self.email

    def sees(self, key):
        """A display key ('page.services', 'profile.<id>', 'companion.<name>', ...) within this person's scope."""
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
_current = contextvars.ContextVar('viewer', default=ADMIN)  # code outside a request (watcher, tests) sees everything


def of(email, admin=None):
    """The viewer for a signed-in email: admin from cluster.json (auth.admins), their agents by owner."""
    email = (email or '').strip().lower()
    admins = {a.lower() for a in cluster.auth().get('admins') or []}
    owned = frozenset(a['id'] for a in cluster.agents().values() if (a.get('owner') or '').lower() == email)
    return Viewer(email, email in admins if admin is None else admin, owned)


def use(viewer):
    _current.set(viewer)


def current():
    return _current.get()
