"""Applies a changed secret where it is used, so editing a file in <data>/secrets (by hand or on the hub's Secrets
screen) takes effect without anyone running a command. What each secret needs is in hub/secrets-map.json ("apply"):
  copy: <path>       install the file at that path for the agent user
  restart: <name>    restart the stack agentlab-<name> (e.g. companion-{companion}); enough for files read at start
  redeploy: <name>   recreate the stack agentlab-<name> (env files are read only when a container is created)
A key may hold {companion} or {agent}; it then matches that file in every companion's or agent's folder.

[hub] extra_secrets (another folder of secrets on this host, with its own map) gets two narrower rules, because its
map lives outside the repo: restart: <container name prefix> (only containers the hub may restart: agentlab's stacks
and [hub] extra_stacks) and copy: <path> (only into an agent's home)."""

import hashlib
import json
import os
import re
import shutil

import cluster

from . import host, store
from .settings import AGENT_UID, AGENTCTL, SECRETS_DIR, SECRETS_MAP


def fingerprints(root=SECRETS_DIR):
    """{path relative to the secrets folder: sha256}; hidden entries (like .versions) are skipped."""
    out = {}
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        for name in sorted(files):
            if name.startswith('.') or name.endswith('.tmp'):
                continue
            full = os.path.join(folder, name)
            with open(full, 'rb') as f:
                out[os.path.relpath(full, root).replace(os.sep, '/')] = hashlib.sha256(f.read()).hexdigest()
    return out


def changes(known, current):
    """([(name, 'added' | 'changed')], [removed names]). The first look (nothing known yet) only records."""
    if not known:
        return [], []
    changed = [(n, 'added' if n not in known else 'changed') for n, h in current.items() if known.get(n) != h]
    return changed, sorted(set(known) - set(current))


def match(rules, name):
    """(rule entry, {placeholder: value}) for a secret file, or (None, {})."""
    if name in rules:
        return rules[name], {}
    for key, entry in rules.items():
        if '{' not in key:
            continue
        pattern = '^' + re.sub(r'\\\{(\w+)\\\}', r'(?P<\1>[a-z0-9-]+)', re.escape(key)) + '$'
        m = re.match(pattern, name)
        if m:
            return entry, m.groupdict()
    return None, {}


def _fill(value, names):
    for k, v in names.items():
        value = value.replace('{' + k + '}', v)
    return value


def _copy(name, dst, _names):
    if not os.path.isdir(os.path.dirname(dst)):
        return False, f'{os.path.dirname(dst)} missing (agent disk not mounted?)'
    shutil.copyfile(os.path.join(SECRETS_DIR, name), dst + '.new')
    os.chown(dst + '.new', AGENT_UID, AGENT_UID)
    os.chmod(dst + '.new', 0o600)
    os.replace(dst + '.new', dst)
    return True, f'installed for the agent ({os.path.basename(dst)})'


def _restart(_name, target, _names):
    stack = f'agentlab-{target}'
    names = [c['name'] for c in store.load('containers.json', {}).get('items') or [] if c.get('stack') == stack]
    if not names:
        return False, f'no running {stack}'
    rc, out = host.run(['docker', 'restart', *names])
    return rc == 0, f'restarted {stack}' if rc == 0 else out[-200:]


def _redeploy(_name, target, _names):
    rc, out = host.run(['python3', AGENTCTL, 'apply', '--stack', f'agentlab-{target}'], timeout=1800)
    return rc == 0, f'recreated agentlab-{target}' if rc == 0 else out[-200:]


RULES = {'copy': _copy, 'restart': _restart, 'redeploy': _redeploy}


def apply(name, rule, names=None):
    kind = next((k for k in RULES if k in rule), None)
    if not kind:
        return False, f'unknown rule {rule}'
    try:
        return RULES[kind](name, _fill(rule[kind], names or {}), names or {})
    except Exception as e:  # one failed rule is reported, the rest still run
        return False, f'{type(e).__name__}: {e}'


def _extra_restart(_name, prefix, _names):
    rows = store.load('containers.json', {}).get('items') or []
    names = [
        c['name'] for c in rows if c.get('name', '').startswith(prefix) and c.get('stack') not in (None, '', 'coolify')
    ]
    if not prefix or not names:
        return False, f'no container {prefix}* the hub may restart'
    rc, out = host.run(['docker', 'restart', *names])
    return rc == 0, f'restarted {", ".join(names)}' if rc == 0 else out[-200:]


def _extra_copy(folder):
    def copy(name, dst, _names):
        homes = [os.path.realpath(f'{a["path"]}/home') + os.sep for a in cluster.load().get('agents') or []]
        real = os.path.realpath(dst)
        if not any(real.startswith(h) for h in homes):
            return False, f"{dst} is not inside an agent's home"
        if not os.path.isdir(os.path.dirname(real)):
            return False, f'{os.path.dirname(dst)} missing'
        shutil.copyfile(os.path.join(folder, name), real + '.new')
        os.chown(real + '.new', AGENT_UID, AGENT_UID)
        os.chmod(real + '.new', 0o600)
        os.replace(real + '.new', real)
        return True, f'installed for the agent ({os.path.basename(real)})'

    return copy


def check_extra(state, extra):
    """What check() does, for the [hub] extra_secrets folder and its map, with only the two narrower rules."""
    folder = (extra or {}).get('folder') or ''
    if not folder or not os.path.isdir(folder):
        state.pop('extra_secrets', None)
        return
    rules = {}
    if extra.get('map'):
        try:
            with open(extra['map']) as f:
                rules = json.load(f)
        except (OSError, ValueError) as e:
            store.event('secret', 'extra secrets map unreadable', str(e), ok=False)
    current = fingerprints(folder)
    changed, removed = changes(state.get('extra_secrets', {}), current)
    allowed = {'restart': _extra_restart, 'copy': _extra_copy(folder)}
    for name, what in changed:
        results = []
        for rule in (rules.get(name) or {}).get('apply', []):
            kind = next((k for k in allowed if k in rule), None)
            if not kind:
                results.append((False, f'rule {rule} is not allowed for extra secrets'))
                continue
            try:
                results.append(allowed[kind](name, str(rule[kind]), {}))
            except Exception as e:  # one failed rule is reported, the rest still run
                results.append((False, f'{type(e).__name__}: {e}'))
        detail = ' · '.join(('✓ ' if good else '✗ ') + msg for good, msg in results)
        ok = all(g for g, _ in results)
        store.event('secret', f'extra/{name} {what}', detail or 'nothing to apply (read when used)', ok=ok)
    for name in removed:
        store.event('secret', f'extra/{name} removed')
    state['extra_secrets'] = current


def check(state):
    try:
        with open(SECRETS_MAP) as f:
            rules = json.load(f)
    except (OSError, ValueError) as e:
        store.event('secret', 'secrets-map.json unreadable', str(e), ok=False)
        return
    current = fingerprints()
    changed, removed = changes(state.get('secrets', {}), current)
    for name, what in changed:
        entry, names = match(rules, name)
        results = [apply(name, rule, names) for rule in (entry or {}).get('apply', [])]
        detail = ' · '.join(('✓ ' if good else '✗ ') + msg for good, msg in results)
        store.event(
            'secret', f'{name} {what}', detail or 'nothing to apply (read when used)', ok=all(g for g, _ in results)
        )
    for name in removed:
        store.event('secret', f'{name} removed')
    state['secrets'] = current
    check_extra(state, (cluster.load().get('hub') or {}).get('extra_secrets'))
