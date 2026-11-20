"""Applies changed secrets per hub/secrets-map.json's copy / restart / redeploy rules."""

import hashlib
import json
import os
import re
import shutil
from collections.abc import Callable
from typing import Literal, TypedDict

import cluster

from . import host, store
from .settings import AGENT_UID, AGENTCTL, SECRETS_DIR, SECRETS_MAP

Change = Literal['added', 'changed']
RuleKind = Literal['copy', 'restart', 'redeploy']
Rule = dict[str, str]  # one {kind: target}, e.g. {"restart": "core"}
Result = tuple[bool, str]  # (ok, message)
Step = Callable[[str, str, dict[str, str]], Result]  # (secret file, target, placeholders)


class MapEntry(TypedDict, total=False):
    apply: list[Rule]  # the other keys are the hub's


SecretsMap = dict[str, MapEntry]  # its "_about" string is never a secret file's name


def fingerprints(root: str = SECRETS_DIR) -> dict[str, str]:
    """{relative path: sha256}, skipping hidden entries."""
    out: dict[str, str] = {}
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        for name in sorted(files):
            if name.startswith('.') or name.endswith('.tmp'):
                continue
            full = os.path.join(folder, name)
            with open(full, 'rb') as f:
                out[os.path.relpath(full, root).replace(os.sep, '/')] = hashlib.sha256(f.read()).hexdigest()
    return out


def changes(known: dict[str, str], current: dict[str, str]) -> tuple[list[tuple[str, Change]], list[str]]:
    """([(name, 'added' | 'changed')], [removed]); the first look only records."""
    if not known:
        return [], []
    changed: list[tuple[str, Change]] = [
        (n, 'added' if n not in known else 'changed') for n, h in current.items() if known.get(n) != h
    ]
    return changed, sorted(set(known) - set(current))


def match(rules: SecretsMap, name: str) -> tuple[MapEntry | None, dict[str, str]]:
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


def with_agent(names: dict[str, str], cfg: cluster.Cluster | None = None) -> dict[str, str]:
    """Adds {agent_home} for a companion's secret: the home of the agent it belongs to."""
    if 'companion' not in names:
        return names
    cfg = cluster.load() if cfg is None else cfg
    agent = next((c.get('agent') for c in cfg.get('companions') or [] if c.get('name') == names['companion']), None)
    path = next((a.get('path') for a in cfg.get('agents') or [] if a.get('id') == agent), None)
    return {**names, 'agent_home': f'{path}/home'} if path else names


def _fill(value: str, names: dict[str, str]) -> str:
    for k, v in names.items():
        value = value.replace('{' + k + '}', v)
    return value


def _copy(name: str, dst: str, _names: dict[str, str]) -> Result:
    if '{' in dst:
        return False, f'no place to install it ({dst})'
    if not os.path.isdir(os.path.dirname(dst)):
        return False, f'{os.path.dirname(dst)} missing (agent disk not mounted?)'
    shutil.copyfile(os.path.join(SECRETS_DIR, name), dst + '.new')
    os.chown(dst + '.new', AGENT_UID, AGENT_UID)
    os.chmod(dst + '.new', 0o600)
    os.replace(dst + '.new', dst)
    return True, f'installed for the agent ({os.path.basename(dst)})'


def _restart(_name: str, target: str, _names: dict[str, str]) -> Result:
    stack = f'agentlab-{target}'
    names = [c['name'] for c in store.load('containers.json', {}).get('items') or [] if c.get('stack') == stack]
    if not names:
        return False, f'no running {stack}'
    rc, out = host.run(['docker', 'restart', *names])
    return rc == 0, f'restarted {stack}' if rc == 0 else out[-200:]


def _redeploy(_name: str, target: str, _names: dict[str, str]) -> Result:
    rc, out = host.run(['python3', AGENTCTL, 'apply', '--stack', f'agentlab-{target}'], timeout=1800)
    return rc == 0, f'recreated agentlab-{target}' if rc == 0 else out[-200:]


RULES: dict[RuleKind, Step] = {'copy': _copy, 'restart': _restart, 'redeploy': _redeploy}


def apply(name: str, rule: Rule, names: dict[str, str] | None = None) -> Result:
    kind = next((k for k in RULES if k in rule), None)
    if not kind:
        return False, f'unknown rule {rule}'
    try:
        return RULES[kind](name, _fill(rule[kind], names or {}), names or {})
    except Exception as e:  # one failed rule is reported, the rest still run
        return False, f'{type(e).__name__}: {e}'


def _extra_restart(_name: str, prefix: str, _names: dict[str, str]) -> Result:
    rows = store.load('containers.json', {}).get('items') or []
    names = [
        c['name'] for c in rows if c.get('name', '').startswith(prefix) and c.get('stack') not in (None, '', 'coolify')
    ]
    if not prefix or not names:
        return False, f'no container {prefix}* the hub may restart'
    rc, out = host.run(['docker', 'restart', *names])
    return rc == 0, f'restarted {", ".join(names)}' if rc == 0 else out[-200:]


def _extra_copy(folder: str) -> Step:
    def copy(name: str, dst: str, _names: dict[str, str]) -> Result:
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


def check_extra(state: store.State, extra: cluster.ExtraSecrets | None) -> None:
    """check() for [hub] extra_secrets: its map lives outside the repo, so only narrow restart/copy rules."""
    folder = (extra.get('folder') or '') if extra else ''
    if not extra or not folder or not os.path.isdir(folder):
        state.pop('extra_secrets', None)
        return
    rules: SecretsMap = {}  # someone else's file: rule targets go through str()
    if extra.get('map'):
        try:
            with open(extra['map']) as f:
                rules = json.load(f)
        except (OSError, ValueError) as e:
            store.event('secret', 'extra secrets map unreadable', str(e), ok=False)
    current = fingerprints(folder)
    changed, removed = changes(state.get('extra_secrets', {}), current)
    allowed: dict[str, Step] = {'restart': _extra_restart, 'copy': _extra_copy(folder)}
    for name, what in changed:
        results: list[Result] = []
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


def check(state: store.State) -> None:
    try:
        with open(SECRETS_MAP) as f:
            rules: SecretsMap = json.load(f)
    except (OSError, ValueError) as e:
        store.event('secret', 'secrets-map.json unreadable', str(e), ok=False)
        return
    current = fingerprints()
    changed, removed = changes(state.get('secrets', {}), current)
    for name, what in changed:
        entry, names = match(rules, name)
        names = with_agent(names)
        results = [apply(name, rule, names) for rule in (entry or {}).get('apply', [])]
        detail = ' · '.join(('✓ ' if good else '✗ ') + msg for good, msg in results)
        store.event(
            'secret', f'{name} {what}', detail or 'nothing to apply (read when used)', ok=all(g for g, _ in results)
        )
    for name in removed:
        store.event('secret', f'{name} removed')
    state['secrets'] = current
    check_extra(state, (cluster.load().get('hub') or cluster.Hub()).get('extra_secrets'))
