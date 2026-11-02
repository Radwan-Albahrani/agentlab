"""The HTTP side, in the edge's two passes.

Pass 1, `/verify` (forwardAuth on every request): who is this (per auth mode), may they, and which agent do they get.
The answer goes back as X-Agentlab-User / -Admin / -Agent, which pass 2 routes on. Pass 1 deletes any client-sent
X-Agentlab-* (and tinyauth's Remote-*) before calling us, so those headers here are always the edge's or tinyauth's.

Pass 2, everything else: the gate's own pages (menu, view switching, "no agent yet"), reached only through the edge
with pass 1's headers set. Agents can't open connections to the gate (nftables), so those headers are trusted here."""

import logging
import os
import re
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import landing
from .config import NONE, host_of, port_of
from .tokens import TokenError, email_of

log = logging.getLogger('gate')
LOCAL = 'local@localhost'
VIEW = 'agentlab_view'
VIEW_PATH = re.compile(r'^/_agentlab/view/([a-z0-9-]+)/?$')


def none_allowed():
    return os.environ.get('GATE_ALLOW_NONE') == '1'


def cookie(headers, name):
    jar = cookies.SimpleCookie()
    try:
        jar.load(headers.get('Cookie') or '')
    except cookies.CookieError:
        return ''
    c = jar.get(name)
    return c.value if c else ''


def _header_email(headers, name):
    email = (headers.get(name) or '').strip().lower()
    if '@' not in email:
        raise TokenError(f'no {name}')
    return email


def identify(cfg, keys, headers, on_domain):
    """The verified email of the caller, or TokenError.
    - cloudflare-access: the Access JWT. On the main domain Cloudflare's email header must also match it, so a forged
      header can't ride along with someone's real token.
    - tailscale: Tailscale-User-Login, set by `tailscale serve` (tagged devices have none and get nothing).
    - tinyauth: Remote-Email, set by tinyauth's forwardAuth answer just before ours."""
    if cfg.mode == 'none':
        if not none_allowed():
            raise TokenError('auth.mode none without GATE_ALLOW_NONE=1')
        return LOCAL
    if cfg.mode == 'tailscale':
        return _header_email(headers, 'Tailscale-User-Login')
    if cfg.mode == 'tinyauth':
        return _header_email(headers, 'Remote-Email')
    if cfg.mode != 'cloudflare-access':
        raise TokenError(f'unknown auth.mode {cfg.mode!r}')
    token = (headers.get('Cf-Access-Jwt-Assertion') or '').strip() or cookie(headers, 'CF_Authorization')
    email = email_of(token, cfg.team, cfg.audience, keys)
    said = headers.get('Cf-Access-Authenticated-User-Email')
    if said is not None and on_domain and said.strip().lower() != email:
        raise TokenError('email header does not match the token')
    return email


def is_t3_path(uri):
    path = urlsplit(uri or '/').path or '/'
    return not (path == '/_agentlab' or path.startswith('/_agentlab/'))


def safe_next(query):
    """Where to go after switching views: a same-site path only, never `//host` or `/\\host` (open redirect)."""
    nxt = (parse_qs(query).get('next') or ['/'])[0]
    ok = nxt.startswith('/') and not nxt.startswith(('//', '/\\')) and not any(c < ' ' or c == '\\' for c in nxt)
    return nxt if ok else '/'


class Handler(BaseHTTPRequestHandler):
    server_version = 'agentlab-gate'
    sys_version = ''
    protocol_version = 'HTTP/1.1'
    timeout = 30

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/health':
            return self._send(200, 'text/plain', b'ok\n')
        if path == '/verify':
            return self._verify()
        return self._page()

    def do_HEAD(self):
        self.do_GET()

    def _other_method(self):
        # Traefik's forwardAuth may keep the original method, so /verify answers them all; the pages are GET only.
        if urlsplit(self.path).path == '/verify':
            return self._verify()
        return self._send(405, 'text/plain', b'Method not allowed\n')

    def do_POST(self):
        self._other_method()

    def do_PUT(self):
        self._other_method()

    def do_PATCH(self):
        self._other_method()

    def do_DELETE(self):
        self._other_method()

    def do_OPTIONS(self):
        self._other_method()

    # ------------------------------------------------------------ pass 1
    def _verify(self):
        cfg = self.server.config.fresh()
        host = self.headers.get('X-Forwarded-Host')
        port = port_of(host, self.headers.get('X-Forwarded-Port'))
        place = cfg.where(host, port, self.headers.get('X-Agentlab-Site'))
        try:
            email = identify(cfg, self.server.keys, self.headers, place == 'domain')
        except TokenError as e:
            return self._deny(host, '-', str(e))
        admin = cfg.mode == 'none' or email in cfg.admins
        ok, why, agent = cfg.decide(place, email, cookie(self.headers, VIEW), admin)
        if not ok:
            return self._deny(host, email, why)
        if place == 'domain' and agent in cfg.owned(email) and is_t3_path(self.headers.get('X-Forwarded-Uri')):
            upstream = cfg.agents[agent].get('upstream') or f'http://agent-{agent}'
            if self.server.onboarding.pending(agent, upstream):
                to = f'{cfg.hub_url()}/agents/{agent}/onboarding'
                return self._send(302, 'text/plain', b'', {'Location': to})
        extra = {'X-Agentlab-User': email, 'X-Agentlab-Admin': '1' if admin else '0', 'X-Agentlab-Agent': agent}
        return self._send(200, 'text/plain', b'ok\n', extra)

    # ------------------------------------------------------------ pass 2
    def _page(self):
        cfg = self.server.config.fresh()
        host = self.headers.get('Host')
        email = (self.headers.get('X-Agentlab-User') or '').strip().lower()
        if not email:
            return self._deny(host, '-', 'page request without pass 1 headers')
        port = port_of(host, self.headers.get('X-Forwarded-Port'))
        if cfg.where(host, port, self.headers.get('X-Agentlab-Site')) != 'domain':
            return self._deny(host, email, 'gate pages live on the main domain only')
        admin = self.headers.get('X-Agentlab-Admin') == '1'
        agent = (self.headers.get('X-Agentlab-Agent') or '').strip()
        current = agent if agent in cfg.agents else NONE
        url = urlsplit(self.path)
        secure = '' if cfg.mode == 'none' else '; Secure'
        if url.path.rstrip('/') == '/_agentlab/view/me':
            return self._redirect(safe_next(url.query), f'{VIEW}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax{secure}')
        m = VIEW_PATH.match(url.path)
        if m:
            if m.group(1) not in cfg.may_open(email, admin):
                return self._deny(host, email, 'not an agent you may open')
            return self._redirect(safe_next(url.query), f'{VIEW}={m.group(1)}; Path=/; HttpOnly; SameSite=Lax{secure}')
        pending = False
        if current in cfg.owned(email):
            upstream = cfg.agents[current].get('upstream') or f'http://agent-{current}'
            pending = self.server.onboarding.pending(current, upstream)
        page = landing.menu(cfg, email, admin, current, pending)
        return self._send(200, 'text/html; charset=utf-8', page.encode())

    def _redirect(self, to, set_cookie):
        self._send(303, 'text/plain', b'', {'Location': to, 'Set-Cookie': set_cookie})

    def _deny(self, host, email, why):
        log.warning('deny host=%s email=%s why=%s', host_of(host) or '-', email, why)
        if 'text/html' in (self.headers.get('Accept') or ''):
            self._send(403, 'text/html; charset=utf-8', landing.denied().encode())
        else:
            self._send(403, 'text/plain', b'Forbidden: not signed in, or not yours.\n')

    def _send(self, status, ctype, body, extra=None):
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # decisions are logged in _deny; per-request access logs would be every asset of every page


def serve(config, keys, onboarding, port):
    server = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    server.daemon_threads = True
    server.config, server.keys, server.onboarding = config, keys, onboarding
    return server
