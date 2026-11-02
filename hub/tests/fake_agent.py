"""Stand-ins for the hub's tests: every agent's Accounts app (image/accounts) — /<agent id>/api/... answers with a
signed-in agent — and, given a watch folder, the host watcher's log requests. Run:
python3 fake_agent.py [port] [watch folder]   (the hub then uses HUB_AGENT_URL=http://127.0.0.1:<port>/{id})"""

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


def flow(key, name, signed_in=True):
    return {
        'key': key,
        'name': name,
        'hint': f'Sign in to {name}.',
        'mode': 'default',
        'signedIn': signed_in,
        'detail': 'signed in as admin@example.com' if signed_in else '',
        'active': False,
        'url': '',
        'code': '',
        'done': False,
        'screen': '',
    }


# admin has finished onboarding; sara hasn't, so the onboarding page has something to do. App pairing works for
# admin (a pair host) and not for sara (no pair_domain), as it would on a cluster without one.
ONBOARDED = {'admin'}
DEVICES = {
    'admin': [
        {
            'id': 's1',
            'label': 'iPhone',
            'ip': '203.0.113.7',
            'userAgent': 'T3 iOS',
            'created': '2026-11-01T09:00:00Z',
            'lastSeen': '2026-11-02T09:00:00Z',
            'expires': '2026-12-01T09:00:00Z',
            'connected': True,
        }
    ],
    'sara': [],
    'lab': [],
}


def onboarding(agent):
    signed = {'claude': True, 'codex': agent == 'admin'}
    ready = any(signed.values())
    steps = [
        {'id': 'claude', 'done': signed['claude'], 'optional': False},
        {'id': 'codex', 'done': signed['codex'], 'optional': False},
        {'id': 'connectors', 'done': True, 'optional': True},
        {'id': 'github', 'done': agent == 'admin', 'optional': True},
    ]
    return {'done': ready and agent in ONBOARDED, 'ready': ready, 'steps': steps}


PAIR_BODIES = []  # what the hub sent, so tests can check it passed the page's host


def pair(agent, kind):
    if kind == 'app' and agent != 'admin':
        return {
            'available': False,
            'reason': "The T3 app needs its own address for this agent (pair_domain), which this cluster doesn't have.",
        }
    host = 'agents.example.com' if kind == 'browser' else f'{agent}-t3.example.com'
    return {
        'available': True,
        'kind': kind,
        'url': f'https://{host}/pair#token=example-{kind}',
        'token': f'example-{kind}',
        'expires': '2030-01-01T00:10:00Z',
        'id': 'p1',
    }


def summary(agent):
    browser = agent == 'admin'  # one agent with its browser open, one without
    return {
        'agent': agent,
        'owner': 'sara@example.com' if agent == 'lab' else f'{agent}@example.com',
        'accounts': {
            'claude': {'signedIn': True, 'detail': 'Claude Max', 'active': False},
            'codex': {'signedIn': agent == 'admin', 'detail': '', 'active': False},
            'github': {'signedIn': agent == 'admin', 'detail': 'example-admin', 'active': False},
        },
        'connectors': {'linear': {'name': 'Linear', 'added': True, 'signedIn': True}},
        'devices': len(DEVICES.get(agent, [])),
        'onboarded': agent in ONBOARDED,
        'resources': {'usedMB': 3100, 'limitMB': 12288, 'running': ['bun test'], 'waiting': [], 'paused': 0},
        'browserUp': browser,
    }


def page(agent):
    github = flow('github', 'GitHub', agent == 'admin')
    github['mcpReady'] = True
    return {
        'agent': agent,
        'owner': 'sara@example.com' if agent == 'lab' else f'{agent}@example.com',
        'notice': '',
        'keys': [{'label': 'Ctrl+C', 'value': 'stop'}],
        'ai': [flow('claude', 'Claude'), flow('codex', 'Codex', agent == 'admin')],
        'github': github,
        'connectors': [
            {'key': 'linear', 'name': 'Linear', 'what': 'Issues', 'added': True, 'custom': False, 'ready': True},
            {'key': 'notion', 'name': 'Notion', 'what': 'Docs', 'added': False, 'custom': False, 'ready': False},
        ],
        'devices': DEVICES.get(agent, []),
        'onboarding': onboarding(agent),
        'env': {'EXAMPLE_TOKEN': {'masked': 'exa…', 'length': 20}},
        'browserUp': agent == 'admin',
    }


class Handler(BaseHTTPRequestHandler):
    def reply(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def split(self):
        _, agent, path = urlparse(self.path).path.split('/', 2)
        return agent, '/' + path

    def do_GET(self):
        agent, path = self.split()
        if path == '/api/summary':
            return self.reply(summary(agent))
        if path == '/api/page':
            return self.reply(page(agent))
        if path == '/api/env/value':
            return self.reply({'key': 'EXAMPLE_TOKEN', 'value': 'example-value'})
        if path == '/api/onboarding':
            return self.reply(onboarding(agent))
        if path == '/api/devices':
            return self.reply({'devices': DEVICES.get(agent, [])})
        return self.reply({'error': 'not found'}, 404)

    def body(self):
        return json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0) or 0)) or b'{}')

    def do_POST(self):
        agent, path = self.split()
        body = self.body()
        if path == '/api/onboarding/finish':
            ONBOARDED.add(agent)
            return self.reply({'ok': True, 'error': None, **onboarding(agent)})
        if path == '/api/pair':
            PAIR_BODIES.append(body)
            return self.reply(pair(agent, body.get('kind')))
        if path == '/api/devices/revoke':
            DEVICES[agent] = [d for d in DEVICES.get(agent, []) if d['id'] != body.get('id')]
            return self.reply({'ok': True, 'error': None})
        if path.startswith('/api/env/'):
            return self.reply({'ok': True, 'errors': [], 'count': 1})
        return self.reply({'ok': True, 'error': None})

    def log_message(self, fmt, *args):
        pass


def answer_logs(watch):
    """What the host watcher does for logs~<container>: write the tail the page then shows."""
    folder = os.path.join(watch, 'requests')
    while True:
        for name in os.listdir(folder) if os.path.isdir(folder) else []:
            action, _, target = name.partition('~')
            if action == 'logs':
                os.makedirs(os.path.join(watch, 'logs'), exist_ok=True)
                with open(os.path.join(watch, 'logs', target + '.txt'), 'w') as f:
                    f.write(f'2026-11-02T10:00:00Z {target} started\n2026-11-02T10:00:01Z {target} ready\n')
                os.remove(os.path.join(folder, name))
        time.sleep(0.3)


if __name__ == '__main__':
    if len(sys.argv) > 2:
        threading.Thread(target=answer_logs, args=(sys.argv[2],), daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', int(sys.argv[1]) if len(sys.argv) > 1 else 8791), Handler).serve_forever()
