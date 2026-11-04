"""/api/page: everything the hub shows for this agent's sign-ins, connectors, devices and env vars, including
live sign-in flows (link, code, terminal), so the web app can render it and poll while a flow runs. /api/act: its
buttons."""

import connectors
import envfile
import onboarding
import pairing
import signin
from util import AGENT_ID, AGENT_OWNER, browser_up, flash, open_callback


def _flow(flow):
    return {
        'key': flow,
        'name': signin.FLOWS[flow]['name'],
        'hint': signin.FLOWS[flow]['hint'],
        'mode': signin.mode(flow),
        **signin.state(flow),
    }


def _connector(key, srv):
    out = {
        'key': key,
        'name': srv['name'],
        'what': srv['what'],
        'added': srv['added'],
        'custom': key not in connectors.CATALOG,
        'ready': srv['added'] and connectors.signed_in(key),
    }
    if srv['added']:
        out['flow'] = connectors.login_state(key)
    return out


def page():
    github = _flow('github')
    github['mcpReady'] = 'github' in connectors.load()
    return {
        'agent': AGENT_ID,
        'owner': AGENT_OWNER,
        'notice': flash(),
        'keys': [{'label': k, 'value': v} for k, v in signin.KEYS.items()],
        'ai': [_flow(f) for f in signin.AI_FLOWS],
        'github': github,
        'tools': [_flow(f) for f in signin.TOOL_FLOWS],
        'connectors': [_connector(k, s) for k, s in connectors.servers().items()],
        'devices': pairing.devices(),
        'onboarding': onboarding.state(),
        'env': envfile.masked(),
        'browserUp': browser_up(),
    }


def act(body):
    """One button on the page -> '' (done) or a message to show. Unknown actions raise ValueError."""
    action, target = body.get('action', ''), body.get('p', '')

    def text(key):
        return str(body.get(key) or '').strip()

    if action == 'token' and target == 'github':
        return signin.save_github_token(text('token'))
    if action.startswith('mcp-'):
        return _connector_action(action, target, text)
    return _signin_action(action, target, text)


def _connector_action(action, name, text):
    if action == 'mcp-custom':
        return connectors.add_custom(text('name').lower(), text('url'))
    if action == 'mcp-add':
        if name not in connectors.CATALOG:
            raise ValueError('Unknown connector.')
        ok, out = connectors.add_shared(name, connectors.CATALOG[name]['url'])
        if not ok:
            return f'Could not add {connectors.CATALOG[name]["name"]}: {out[:200]}'
        connectors.start_login(name)
        return ''
    srv = connectors.servers().get(name)
    if not srv or not srv['added']:
        raise ValueError('Unknown connector.')
    if action == 'mcp-login':
        connectors.start_login(name)
    elif action == 'mcp-send':
        if not connectors.LOCAL_CALLBACK_RE.match(text('text')):
            return 'Paste the whole address the browser landed on (it starts with localhost: or 127.0.0.1:).'
        open_callback(text('text'))
    elif action == 'mcp-stop':
        connectors.stop_session(connectors.flow(name))
    elif action == 'mcp-remove':
        connectors.remove(name)
    else:
        raise ValueError('Unknown action.')
    return ''


def _signin_action(action, flow, text):
    if flow not in signin.FLOWS:
        raise ValueError('Unknown sign-in.')
    handlers = {
        'start': lambda: signin.start(flow, text('how') or 'default'),
        'send': lambda: signin.send(flow, text('text')),
        'key': lambda: signin.key(flow, text('key')),
        'stop': lambda: signin.stop(flow),
        'logout': lambda: signin.logout(flow),
    }
    if action not in handlers:
        raise ValueError('Unknown action.')
    handlers[action]()
    return ''
