"""The owner's env vars for this agent, sourced by every agent bash via /etc/agent/load-env.sh."""

import os
import re

from util import HOME, sh_quote

ENV_FILE = os.path.join(HOME, '.config', 'agent', 'env')
KEY_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,127}$')
LINE_RE = re.compile(r"^export ([A-Za-z_][A-Za-z0-9_]*)='(.*)'$")
PROTECTED = {
    'PATH',
    'HOME',
    'USER',
    'SHELL',
    'PWD',
    'DISPLAY',
    'XDG_RUNTIME_DIR',
    'DOCKER_HOST',
    'BASH_ENV',
    'TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE',
    'TESTCONTAINERS_HOST_OVERRIDE',
    'NPM_CONFIG_PREFIX',
    'AGENT_ID',
    'AGENT_OWNER',
    'AGENTLAB_DOMAIN',
    'AGENTLAB_HUB_DOMAIN',
    'AGENTLAB_PAIR_HOST',
    'AGENTLAB_AUTH_MODE',
    'AGENTLAB_ISOLATION',
    'AGENTLAB_WAIT_NETWORK',
    'AGENTLAB_COMPANIONS',
    'AGENTLAB_PUBLISHED',
    'AGENTLAB_PUBLISHED_HUB',
    'ANDROID_HOME',
    'ANDROID_SDK_ROOT',
    'ANDROID_AVD_HOME',
    'LD_PRELOAD',
    'LD_LIBRARY_PATH',
}


def load():
    try:
        with open(ENV_FILE) as f:
            lines = f.read().splitlines()
    except OSError:
        return {}
    return {m.group(1): m.group(2).replace("'\\''", "'") for m in map(LINE_RE.match, lines) if m}


def save(env):
    os.makedirs(os.path.dirname(ENV_FILE), exist_ok=True)
    tmp = ENV_FILE + '.tmp'
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as f:
        f.write('# Managed by the Accounts page. One variable per line; values are single-quoted.\n')
        f.writelines(f'export {k}={sh_quote(env[k])}\n' for k in sorted(env))
    os.replace(tmp, ENV_FILE)


def check(key):
    """-> '' if the name may be set, else why not."""
    if not KEY_RE.match(key):
        return f'"{key}" is not a valid name (letters, digits, underscore; not starting with a digit).'
    if key.upper() in PROTECTED:
        return f"{key} is managed by the system and can't be changed here."
    return ''


def parse(text):
    """Pasted .env text -> (dict, errors)."""
    out, errors = {}, []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        m = re.match(r'^(?:export\s+)?([^=\s]+)\s*=\s*(.*)$', line)
        if not m:
            errors.append(f'skipped: {line[:40]}')
            continue
        key, value = m.groups()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
            value = value[1:-1]
        if err := check(key):
            errors.append(err)
        else:
            out[key] = value
    return out, errors


def masked():
    return {k: {'masked': f'…{v[-4:]}' if len(v) > 8 else '•' * len(v), 'length': len(v)} for k, v in load().items()}


def apply(action, body):
    """set {key, value} / delete {key} / import {text} -> (ok, errors, count)."""
    env = load()
    key = str(body.get('key') or '').strip()
    if action == 'set':
        if err := check(key):
            return False, [err], len(env)
        env[key] = str(body.get('value') or '')
        errors = []
    elif action == 'delete':
        env.pop(key, None)
        errors = []
    else:
        new, errors = parse(str(body.get('text') or ''))
        env.update(new)
    save(env)
    return not errors, errors, len(env)
