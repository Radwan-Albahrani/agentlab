"""Requests an agent makes about its own companions, as files on its own disk (it has no network path to anything
shared): ~/.agentlab/requests/<action>~companion~<name>, the payload (if any) JSON in the file. Actions:
create {display_name, kind} · remove · secret {key, value} · settings {...} · restart · stop · start.
Ownership follows from the path: every action but create works only on a companion of the agent whose home holds
the request. Results go to ~/.agentlab/results/<same name>.json as {ok, message}. A request file is deleted as soon
as it is read (it may hold a secret), and secret values never reach a result, an event or a log.
The folders are the agent's, so everything goes through safe.Folder."""

import json
import os
import re
import time

import cluster
from safe import Folder

from . import host, store
from .settings import AGENTCTL, DATA

NAME = re.compile(r'^(create|remove|secret|settings|restart|stop|start)~companion~([a-z0-9][a-z0-9-]{0,28}[a-z0-9])$')
MAX_PAYLOAD = 64 * 1024
MAX_PER_TICK = 20  # an agent flooding its folder can't keep the watcher busy
SECRET_KEYS = {
    'owner.txt',
    'bot-token.txt',
    'app-token.txt',
    'user-token.txt',
    'github-app-id.txt',
    'github-app-key.pem',
    'work-tools.md',
}


def parse(filename):
    m = NAME.match(filename)
    return (m.group(1), m.group(2)) if m else None


def companion_containers(name):
    """Asked from Docker itself (stopped ones too): the inventory snapshot is up to 30 s old, and a companion its agent
    just created, or one down because it isn't configured yet, must still be restartable. The inventory covers stacks
    Coolify names by its own uuid."""
    stack = f'agentlab-companion-{name}'
    rc, out = host.run(
        ['docker', 'ps', '-a', '--filter', f'label=com.docker.compose.project={stack}', '--format', '{{.Names}}']
    )
    names = out.split() if rc == 0 else []
    return names or [c['name'] for c in store.load('containers.json', {}).get('items') or [] if c.get('stack') == stack]


def _docker(action, name, _agent, _payload):
    names = companion_containers(name)
    if not names:
        return False, f'companion {name} has no container yet'
    rc, out = host.run(['docker', action, *names], timeout=180)
    return rc == 0, f'{action} {name}: done' if rc == 0 else out[-300:]


def _agentctl(*args):
    rc, out = host.run(['python3', AGENTCTL, '--json', *args], timeout=1800)
    try:
        reply = json.loads(out[out.index('{') :])
    except ValueError:
        return False, out[-300:] or f'agentctl exited {rc}'
    return reply.get('ok', False), reply.get('error') or '; '.join(reply.get('messages') or []) or 'done'


def _create(_action, name, agent, payload):
    display = str(payload.get('display_name') or name)[:60]
    kind = str(payload.get('kind') or 'slack')
    return _agentctl('companion', 'create', agent, name, '--display-name', display, '--kind', kind)


def _remove(_action, name, agent, _payload):
    return _agentctl('companion', 'remove', agent, name)


def _secret(_action, name, _agent, payload):
    key, value = payload.get('key'), payload.get('value')
    if key not in SECRET_KEYS:
        return False, f'unknown secret {key!r}; known: {", ".join(sorted(SECRET_KEYS))}'
    if not isinstance(value, str) or not value.strip():
        return False, 'the secret value must be a non-empty string'
    os.makedirs(f'{DATA}/secrets/companions', mode=0o700, exist_ok=True)  # the host's own folder, not the agent's
    with Folder(f'{DATA}/secrets/companions', name, create=True) as f:
        f.write(key, value.strip() + '\n', mode=0o600)
    return True, f'{key} saved for {name}; it restarts within a minute to pick it up'


def _settings(_action, name, _agent, payload):
    os.makedirs(f'{DATA}/companions', exist_ok=True)
    with Folder(f'{DATA}/companions', name, create=True) as f:
        current = f.read_json('settings.json')
        merged = {**(current if isinstance(current, dict) else {}), **payload}
        f.write('settings.json', json.dumps(merged, indent=1) + '\n')
    return True, f'settings of {name} updated: {", ".join(sorted(payload)) or "nothing"}'


HANDLERS = {
    'create': _create,
    'remove': _remove,
    'secret': _secret,
    'settings': _settings,
    'restart': _docker,
    'stop': _docker,
    'start': _docker,
}


def decide(action, name, agent, mine, payload):
    """(ok, message): the checks every request passes before anything happens."""
    if action != 'create' and name not in mine:
        return False, f'{name} is not one of your companions'
    if action in ('create', 'secret', 'settings') and not isinstance(payload, dict):
        return False, 'this request needs a JSON object in the file'
    return HANDLERS[action](action, name, agent, payload)


def _payload(text):
    if not text or not text.strip():
        return {}
    try:
        return json.loads(text)
    except ValueError:
        return None


def handle(agent, mine):
    home = os.path.join(agent['path'], 'home')
    if not os.path.isdir(home):
        return
    try:
        requests = Folder(home, '.agentlab/requests')
    except (FileNotFoundError, NotADirectoryError):
        return
    except OSError as e:  # a symlink where the folder should be, and the like
        store.event('agent', f'{agent["id"]}: request folder refused', type(e).__name__, ok=False)
        return
    with requests:
        for filename in requests.names()[:MAX_PER_TICK]:
            parsed = parse(filename) if requests.is_file(filename) else None
            text = requests.read(filename, MAX_PAYLOAD + 1) if parsed else None
            requests.remove(filename)  # first: it may hold a secret
            if not parsed:
                continue
            action, name = parsed
            if text is not None and len(text) > MAX_PAYLOAD:
                ok, message = False, f'the request is larger than {MAX_PAYLOAD // 1024} KB'
            else:
                try:
                    ok, message = decide(action, name, agent['id'], mine, _payload(text))
                except Exception as e:  # reported to the agent; never the payload
                    ok, message = False, f'{action} failed: {type(e).__name__}'
            result = {'at': time.time(), 'action': action, 'companion': name, 'ok': ok, 'message': message}
            try:
                with Folder(home, '.agentlab/results', create=True) as results:
                    results.write(filename + '.json', json.dumps(result))
            except OSError as e:
                message += f' (result not written: {type(e).__name__})'
            store.event('companion', f'{agent["id"]}: {action} {name}', message, ok=ok)


def handle_all():
    cfg = cluster.load()
    owned = {}
    for c in cfg.get('companions') or []:
        owned.setdefault(c.get('agent'), set()).add(c.get('name'))
    for a in cfg.get('agents') or []:
        if a.get('id') and a.get('path'):
            handle(a, owned.get(a['id'], set()))
