"""T3's own MCP tools, called with a short-lived token: answer a chat's pending question or interrupt its run
(the actions the companion can't do through `t3 thread`)."""

import json
import subprocess
import urllib.request

T3_MCP = 'http://127.0.0.1:3773/mcp'
PROTOCOL = '2025-06-18'


class Client:
    """Minimal MCP client over streamable HTTP (JSON or SSE replies)."""

    def __init__(self, token):
        self.token, self.session, self.next_id = token, None, 0
        self._rpc(
            'initialize',
            {
                'protocolVersion': PROTOCOL,
                'capabilities': {},
                'clientInfo': {'name': 'companion-bridge', 'version': '1'},
            },
        )
        self._rpc('notifications/initialized', notify=True)

    def call(self, name, args):
        res = self._rpc('tools/call', {'name': name, 'arguments': args})
        if res.get('isError'):
            raise RuntimeError(' '.join(c.get('text', '') for c in res.get('content', []))[:400])
        if 'structuredContent' in res:
            return res['structuredContent']
        text = ''.join(c.get('text', '') for c in res.get('content', []))
        try:
            return json.loads(text)
        except ValueError:
            return text

    def _rpc(self, method, params=None, notify=False):
        body = {'jsonrpc': '2.0', 'method': method, 'params': params or {}}
        if not notify:
            self.next_id += 1
            body['id'] = self.next_id
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream',
            'MCP-Protocol-Version': PROTOCOL,
        }
        if self.session:
            headers['Mcp-Session-Id'] = self.session
        with urllib.request.urlopen(
            urllib.request.Request(T3_MCP, json.dumps(body).encode(), headers), timeout=60
        ) as r:
            self.session = r.headers.get('Mcp-Session-Id') or self.session
            raw = r.read().decode()
        if notify or not raw.strip():
            return {}
        if not raw.lstrip().startswith('{'):  # SSE: the last data line is the reply
            raw = [line[5:].strip() for line in raw.splitlines() if line.startswith('data:')][-1]
        res = json.loads(raw)
        if 'error' in res:
            raise RuntimeError(res['error'].get('message', str(res['error'])))
        return res.get('result', {})


def _t3(*args):
    return subprocess.run(['t3', *args], capture_output=True, text=True, timeout=30, cwd='/workspace', check=False)


def with_tools(label, work):
    """Run work(client) with a 5-minute token, revoked straight after -> (ok, detail)."""
    p = _t3(
        'auth',
        'session',
        'issue',
        '--json',
        '--ttl',
        '5m',
        '--label',
        label,
        '--subject',
        'mcp-client',  # /mcp only accepts MCP client sessions
        '--scope',
        'orchestration:read',
        '--scope',
        'orchestration:operate',
    )
    try:
        issued = json.loads(p.stdout)
    except ValueError:
        return False, f'token: {(p.stderr or p.stdout)[-300:]}'
    token = issued.get('token') or issued.get('accessToken') or issued.get('bearerToken', '')
    session_id = issued.get('sessionId') or issued.get('id', '')
    try:
        return work(Client(token))
    except Exception as e:  # any failure goes back to the companion, not into the server
        return False, f'{type(e).__name__}: {e}'[:400]
    finally:
        if session_id:
            _t3('auth', 'session', 'revoke', session_id)


def answer(thread, message):
    """Answer the chat's pending question(s) the way the app's answer box does."""

    def work(t3):
        pending = t3.call('t3_pending_request_list', {'threadId': thread}).get('requestIds', [])
        if not pending:
            return False, 'no pending question'
        for request in pending:
            questions = t3.call('t3_pending_request_read', {'threadId': thread, 'requestId': request}).get(
                'questions', []
            )
            t3.call(
                't3_pending_request_respond',
                {
                    'threadId': thread,
                    'requestId': request,
                    'answers': {q['id']: message for q in questions} or {'0': message},
                },
            )
        return True, {'answered': pending}

    return with_tools('companion answer', work)


def interrupt(thread):
    return with_tools('companion stop', lambda t3: (True, t3.call('t3_thread_interrupt', {'threadId': thread})))
