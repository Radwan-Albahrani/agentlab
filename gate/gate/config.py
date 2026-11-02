"""cluster.json as the gate needs it, re-read whenever the file changes so `agentctl apply` never needs a restart.
A missing or broken file leaves the last good one in place, or an empty config that denies everything."""

import json
import logging
import os
import re
import threading

log = logging.getLogger('gate')
TEAM = re.compile(r'^[a-z0-9][a-z0-9-]{0,62}$')  # ends up in the certs URL, so nothing else gets through
GATE, NONE = 'gate', 'none'  # X-Agentlab-Agent values that aren't agents: the gate's own pages / no agent
SITES = {'agent': 'domain', 'hub': 'hub', 'coolify': 'coolify'}  # X-Agentlab-Site -> place


def host_of(raw):
    """'Agents.Example.com:443' -> 'agents.example.com'. Hostnames are case-insensitive, so every comparison goes
    through here: matching them case-sensitively lets a mixed-case host slip past its rule (tinyauth CVE-2026-77560)."""
    host = (raw or '').split(',')[0].strip().lower()
    if host.startswith('['):
        return host.split(']')[0] + ']'
    return (host.rsplit(':', 1)[0] if ':' in host else host).rstrip('.')


def port_of(raw_host, forwarded_port):
    """The port the person connected to: X-Forwarded-Port, else the one in the Host header, else ''."""
    port = (forwarded_port or '').split(',')[0].strip()
    if port:
        return port
    host = (raw_host or '').split(',')[0].strip()
    tail = host.rsplit(']', 1)[-1]
    return tail.rsplit(':', 1)[1] if ':' in tail else ''


def _email(v):
    return v.strip().lower() if isinstance(v, str) else ''


class Config:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._mtime = None
        self._apply({})

    def fresh(self):
        """Reload when the file changed; cheap enough (one stat) to call on every request."""
        try:
            mtime = os.stat(self.path).st_mtime_ns
        except OSError:
            return self
        if mtime == self._mtime:
            return self
        with self._lock:
            if mtime != self._mtime:
                try:
                    with open(self.path, encoding='utf-8') as f:
                        self._apply(json.load(f))
                    log.info('config loaded: mode %s, %d agents', self.mode, len(self.agents))
                except (OSError, ValueError, TypeError, AttributeError, KeyError) as e:
                    log.error('config %s unreadable, keeping the previous one: %s', self.path, e)
                self._mtime = mtime
        return self

    def _apply(self, raw):
        auth = raw.get('auth') or {}
        cf = auth.get('cloudflare') or {}
        team = _email(cf.get('team'))
        self.mode = auth.get('mode') or 'cloudflare-access'
        self.team = team if TEAM.match(team) else ''
        self.audience = str(cf.get('audience') or '').strip()
        self.hub_port = str(auth.get('hub_port') or 8443)
        self.admins = {_email(e) for e in auth.get('admins') or []} - {''}
        self.agents = {a['id']: {**a, 'owner': _email(a.get('owner'))} for a in raw.get('agents') or [] if a.get('id')}
        self.domain = host_of(raw.get('domain'))
        self.hub_domain = host_of(raw.get('hub_domain'))
        self.coolify_domain = host_of(raw.get('coolify_domain'))
        self.name = raw.get('name') or 'agentlab'

    def hub_url(self):
        """Where the hub is for people: its own name, or on Tailscale the same name on auth.hub_port."""
        if self.mode == 'tailscale' and (not self.hub_domain or self.hub_domain == self.domain):
            return f'https://{self.domain}:{self.hub_port}'
        return f'https://{self.hub_domain or self.domain}'

    def owned(self, email):
        """The agents this person owns, by id. A person may own several."""
        return [i for i in sorted(self.agents) if self.agents[i]['owner'] == email]

    def may_open(self, email, admin):
        return sorted(self.agents) if admin else self.owned(email)

    def chosen(self, email, view, admin):
        """The agent the main domain reaches: the `agentlab_view` cookie if it names one you may open, else your only
        agent, else '' (the gate's picker). A cookie naming anything else is ignored, never an error."""
        if view and view in self.may_open(email, admin):
            return view
        own = self.owned(email)
        return own[0] if len(own) == 1 else ''

    def where(self, host, port, site=None):
        """'hub', 'coolify', 'domain' or '' (refuse) for a request. The edge stamps which site was asked for
        (X-Agentlab-Site: agent | hub | coolify), which is how Tailscale serves agents and hub on one name; the host
        must still be one of the cluster's names. Without the header, the host (and on Tailscale the port) decides."""
        host = host_of(host)
        names = {self.domain, self.hub_domain, self.coolify_domain} - {''}
        if not host or host not in names:
            return ''
        if site is not None:
            place = SITES.get(site.strip().lower(), '')
            return '' if place == 'coolify' and not self.coolify_domain else place
        if self.mode == 'tailscale' and host == self.domain and port == self.hub_port:
            return 'hub'
        if host == self.hub_domain:
            return 'hub'
        if host == self.coolify_domain:
            return 'coolify'
        return 'domain' if host == self.domain else ''

    def decide(self, place, email, view, admin):
        """(allowed, why, agent) for a verified email at a place from where(). `agent` becomes X-Agentlab-Agent."""
        own = self.owned(email)
        if place == 'hub':
            ok = admin or bool(own)
            return ok, 'hub' if ok else 'no agent', self.chosen(email, view, admin) or NONE
        if place == 'coolify':
            return admin, 'admin' if admin else 'admins only', NONE
        if place == 'domain':
            return True, 'domain', self.chosen(email, view, admin) or GATE
        return False, 'unknown host or site', NONE
