#!/usr/bin/env python3
"""Accounts app for one agent (port 8790; the edge serves it at /_agentlab/accounts/ with the prefix stripped), JSON
only; the hub renders it:
  GET  /api/page               sign-ins, connectors, devices, env vars (page)       /api/summary  the agent's card
  GET  /api/state?p=<flow>     one live sign-in (also mcp-<name>)                   /api/env/value?k=<name>
  POST /api/act                one button: {action, p, ...} (page.act)              /api/env/set|delete|import
  GET  /api/onboarding         {done, ready, steps}                                  POST /api/onboarding/finish
  POST /api/pair {kind, label, host?} one-time T3 pairing link (browser | app)    GET  /api/devices
  POST /api/devices/revoke {id}                                                    POST /api/t3/*  companion bridge
No login of its own: people reach it only through the edge, whose gate checks who signed in and that this is their
agent; the hub and gate call it over the agent's own network, which no other agent can reach. The bridge also needs
its key."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import bridge
import connectors
import envfile
import onboarding
import page
import pairing
import signin
import summary
from util import AGENT_ID, browser_up, public_url

PORT = 8790
ENV_ACTIONS = ('set', 'delete', 'import')


# "Browser" while the agent has no browser open: the viewer only runs alongside one, so say so and check again.
NO_BROWSER = (
    '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    '<meta http-equiv="refresh" content="5"><title>No browser open</title>'
    '<style>body{font:16px/1.5 system-ui,sans-serif;margin:0;display:grid;place-items:center;min-height:100vh;'
    'background:#f5f5f7;color:#1d1d1f}@media(prefers-color-scheme:dark){body{background:#000;color:#f5f5f7}}'
    'main{max-width:28rem;padding:1.5rem}p{color:#86868b}</style>'
    "<main><h1>No browser open right now</h1><p>The agent's screen appears here while it uses Chrome (for example"
    ' when it tests a page). This page checks again every few seconds.</p></main>'
)


class Handler(BaseHTTPRequestHandler):
    def reply(self, code=200, body='', ctype='application/json', location=None):
        self.send_response(code)
        if location:
            self.send_header('Location', location)
        self.send_header('Content-Type', ctype)
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body.encode())

    def json(self, obj, code=200):
        self.reply(code, json.dumps(obj, default=str))

    def body(self):
        try:
            return json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0) or 0)) or b'{}')
        except ValueError:
            return None

    def do_GET(self):
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        flow = query.get('p', '')
        host = self.headers.get('X-Forwarded-Host') or self.headers.get('Host', '')
        proto = self.headers.get('X-Forwarded-Proto', 'https')
        if url.path == '/health':
            return self.reply(200, 'ok', 'text/plain')
        if url.path == '/':  # the page lives in the hub
            hub = public_url('hub', host, proto)
            if not hub:
                return self.reply(404, 'open this page from the hub', 'text/plain')
            return self.reply(302, '', 'text/plain', f'{hub}/agents/{AGENT_ID}/accounts')
        if url.path == '/api/page':
            return self.json(page.page())
        if url.path == '/api/summary':
            return self.json(summary.summary())
        if url.path == '/api/onboarding':
            return self.json(onboarding.state())
        if url.path == '/api/devices':
            return self.json({'devices': pairing.devices()})
        if url.path == '/api/state' and flow in signin.FLOWS:
            return self.json(signin.state(flow))
        if url.path == '/api/state' and flow.startswith('mcp-') and flow[4:] in connectors.load():
            return self.json(connectors.login_state(flow[4:]))
        if url.path == '/api/env/value':
            key = query.get('k', '')
            return self.json({'key': key, 'value': envfile.load().get(key)})
        if url.path == '/browser':  # the viewer runs only while a browser is open
            if browser_up() and (view := public_url('browser', host, proto)):
                ws = f'{urlparse(view).path.strip("/")}/websockify'.lstrip('/')  # under the edge's path prefix, if any
                return self.reply(302, '', 'text/plain', f'{view}/vnc.html?autoconnect=1&resize=scale&path={ws}')
            return self.reply(503, NO_BROWSER, 'text/html; charset=utf-8')
        return self.reply(404, 'not found', 'text/plain')

    def do_POST(self):
        path = urlparse(self.path).path
        body = self.body()
        if body is None:
            return self.json({'ok': False, 'error': 'bad json'}, 400)
        if path in bridge.ROUTES:
            ok, err = bridge.authorized(self.headers.get('X-Agent-Key', ''))
            if not ok:
                return self.json({'error': err}, 403)
            code, reply = bridge.handle(path, body)
            return self.json(reply, code)
        action = path.rsplit('/', 1)[1]
        if path.startswith('/api/env/') and action in ENV_ACTIONS:
            ok, errors, count = envfile.apply(action, body)
            return self.json({'ok': ok, 'errors': errors, 'count': count}, 200 if ok else 400)
        if path == '/api/onboarding/finish':
            err = onboarding.finish()
            return self.json({'ok': not err, 'error': err or None, **onboarding.state()}, 409 if err else 200)
        if path == '/api/pair':
            try:
                return self.json(
                    pairing.pair(str(body.get('kind', '')), str(body.get('label') or ''), str(body.get('host') or ''))
                )
            except ValueError as e:
                return self.json({'ok': False, 'error': str(e)}, 400)
        if path == '/api/devices/revoke':
            err = pairing.revoke(str(body.get('id', '')))
            code = 404 if err == pairing.NO_DEVICE else 502 if err else 200
            return self.json({'ok': not err, 'error': err or None}, code)
        if path == '/api/act':
            try:
                err = page.act(body)
            except ValueError as e:
                return self.json({'ok': False, 'error': str(e)}, 400)
            return self.json({'ok': not err, 'error': err or None})
        return self.reply(404, 'not found', 'text/plain')

    def log_message(self, fmt, *args):
        pass


def main():
    threading.Thread(target=connectors.migrate, daemon=True).start()
    for flow in signin.FLOWS:  # warm the status cache
        threading.Thread(target=signin.refresh, args=(flow,), daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()


if __name__ == '__main__':
    main()
