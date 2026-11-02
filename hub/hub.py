#!/usr/bin/env python3
"""The hub (port 8080): the web app (static/, built from web/) and its JSON API (routes.py), for everyone with an
agent, each scoped to their own (scope.py); admins see everything. Every request except /health names a signed-in
person (access.py) or gets 403; POSTs must also come from this page (Origin check)."""

import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I leaves the script's folder off the path
import access
import cluster
import notify
import routes
import scope

PORT = int(os.environ.get('HUB_PORT', '8080'))
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body=b'', ctype='application/json', cache='no-store'):
        body = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', cache)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        self.wfile.write(body)

    def json(self, obj, code=200):
        self.send(code, json.dumps(obj, default=str))

    def allowed(self, api):
        try:
            scope.use(access.viewer(self.headers))
            cluster.use_host(self.headers.get('Host', ''))
        except access.DeniedError as e:
            if api:
                self.json({'ok': False, 'error': f'not allowed: {e}'}, 403)
            else:
                self.send(403, f'Not allowed ({e}).', 'text/plain; charset=utf-8')
            return False
        return True

    def static(self, path):
        """Hashed assets are cached for good; every other path is the app (it routes in the browser)."""
        f = os.path.realpath(os.path.join(STATIC, path.lstrip('/')))
        if f.startswith(STATIC + os.sep) and os.path.isfile(f):
            cache = 'public, max-age=31536000, immutable' if path.startswith('/assets/') else 'no-cache'
            self.send(200, Path(f).read_bytes(), mimetypes.guess_type(f)[0] or 'application/octet-stream', cache)
        elif path.startswith('/assets/'):
            self.send(404, 'not found', 'text/plain')
        else:
            self.send(200, Path(STATIC, 'index.html').read_bytes(), 'text/html; charset=utf-8', 'no-cache')

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == '/health':
            return self.send(200, 'ok', 'text/plain')
        api = u.path.startswith('/api/')
        if not self.allowed(api):
            return None
        if not api:
            return self.static(u.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            handler, groups = routes.resolve(routes.GET, u.path.rstrip('/'))
            self.json(handler(groups, q, self.headers.get('Host', '')))
        except routes.ForbiddenError:
            self.json({'error': 'not yours'}, 403)
        except routes.NotFoundError:
            self.json({'error': 'not found'}, 404)
        except ValueError as e:
            self.json({'error': str(e)}, 400)
        return None

    def do_POST(self):
        path = urlparse(self.path).path.rstrip('/')
        origin = self.headers.get('Origin')
        if origin and urlparse(origin).netloc != self.headers.get('Host'):
            return self.json({'ok': False, 'error': 'cross-site request refused'}, 403)
        if not self.allowed(True):
            return None
        try:
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0) or 0)) or b'{}')
            handler, groups = routes.resolve(routes.POST, path)
            self.json({'ok': True, 'message': handler(groups, body, self.headers.get('Host', ''))})
        except routes.ForbiddenError:
            self.json({'ok': False, 'error': 'not yours'}, 403)
        except routes.NotFoundError:
            self.json({'ok': False, 'error': 'not found'}, 404)
        except (ValueError, KeyError, OSError) as e:
            self.json({'ok': False, 'error': str(e).strip("'")}, 400)
        return None

    def log_message(self, fmt, *args):
        pass


if __name__ == '__main__':
    if notify.enabled():  # phone pushes only once a Bark server is configured
        notify.watcher = notify.Watcher(cluster.ids)
        notify.watcher.start()
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
