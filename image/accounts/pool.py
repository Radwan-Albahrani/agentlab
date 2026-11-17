"""This agent's own account pool: a TeamClaude proxy on loopback that rotates Claude Code and Codex across the owner's
accounts. Claude and Codex are pointed at it only while it holds an account for them; otherwise they go direct."""

import base64
import json
import os
import re
import secrets
import subprocess
import threading
import tomllib

from util import active, http, run, screen, session, sh_quote, start_session, stop_session, tmux, type_into

HOME = os.path.expanduser('~')
CONFIG = os.path.join(HOME, '.config', 'teamclaude.json')
CLAUDE_SETTINGS = os.path.join(HOME, '.claude', 'settings.json')
CODEX_CONFIG = os.path.join(os.environ.get('CODEX_HOME') or os.path.join(HOME, '.codex'), 'config.toml')
T3_SETTINGS = os.path.join(HOME, '.t3', 'userdata', 'settings.json')
T3_SECRETS = os.path.join(HOME, '.t3', 'userdata', 'secrets')
SUPERVISOR = ['supervisorctl', '-c', '/etc/agent-supervisord.conf']

PORT = 3456
URL = f'http://127.0.0.1:{PORT}'
PROVIDER = 'agentlab_pool'  # Codex model_providers key
T3_SOURCE = 'agentlab-pool'  # T3 usageLimitSources key
CODEX_LINE = f'model_provider = "{PROVIDER}"  # agentlab-pool'
CODEX_BLOCK = re.compile(r'\n*# BEGIN agentlab-pool\n.*?# END agentlab-pool\n?', re.S)
# What the pool needs; everything else in the file is TeamClaude's own.
SETTINGS = {'host': '127.0.0.1', 'port': PORT, 'cliproxyApi': 'read'}
# Updates come from tools.sh; the probe keeps idle accounts' bars current; pooled quota headers keep Claude Code and T3
# from warning about (or pausing on) one account's limit while another can still take over.
TOP = {'autoUpdate': False, 'quotaProbeSeconds': 300, 'poolQuotaHeaders': True}

FLOWS = {
    'pool-claude': {
        'name': 'Claude',
        'provider': 'claude',
        'login': 'agent-teamclaude login --token',
        'hint': 'Sign in with the Claude account to add. The page then shows a code: paste it below.',
    },
    'pool-codex': {
        'name': 'Codex',
        'provider': 'codex',
        'login': 'agent-teamclaude login --codex --no-browser',
        'hint': 'Sign in with the ChatGPT account to add.',
    },
}
DONE_RE = re.compile(r'^Saved to ', re.M)
URL_RE = re.compile(r'https://\S+')
_sync_lock = threading.Lock()


def _load(path):
    """The JSON in path; None when missing or unreadable (callers leave an unreadable file alone)."""
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _readable(path):
    return not os.path.exists(path) or _load(path) is not None


def _write(path, text):
    """Atomic, so a reader never sees half a file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f'{path}.agentlab-tmp'
    with open(tmp, 'w') as f:
        f.write(text)
    os.replace(tmp, path)


def _write_json(path, data):
    _write(path, json.dumps(data, indent=2) + '\n')


def provider(a):
    """'codex' or 'claude' (TeamClaude's config leaves Claude's out; its status calls it 'anthropic')."""
    return 'codex' if a.get('provider') == 'codex' else 'claude'


def accounts(config=None):
    """The configured accounts: [{name, provider, disabled}]."""
    config = _load(CONFIG) if config is None else config
    return [
        {'name': a.get('name', ''), 'provider': provider(a), 'disabled': bool(a.get('disabled'))}
        for a in (config or {}).get('accounts') or []
        if a.get('type', 'oauth') == 'oauth'
    ]


def wanted(accts):
    """-> (route Claude, route Codex): a provider goes through the pool while it has an enabled account."""
    on = {a['provider'] for a in accts if not a['disabled']}
    return 'claude' in on, 'codex' in on


# --- the files each client reads at launch; each edit leaves alone what the owner set themselves


def seed_config(config):
    """TeamClaude's config with the pool's settings in place -> (config, changed)."""
    config = dict(config or {})
    proxy = dict(config.get('proxy') or {})
    changed = False
    for key, value in SETTINGS.items():
        if proxy.get(key) != value:
            proxy[key], changed = value, True
    if not proxy.get('apiKey'):  # T3's usage source needs a key; TeamClaude only makes one in a config it creates
        proxy['apiKey'], changed = f'tc-{secrets.token_urlsafe(24)}', True
    for key, value in TOP.items():
        if key not in config:
            config[key], changed = value, True
    config['proxy'] = proxy
    config.setdefault('accounts', [])
    return config, changed


def claude_settings(settings, on):
    """~/.claude/settings.json with env.ANTHROPIC_BASE_URL on the pool (on) or without our value -> new or None."""
    settings = dict(settings or {})
    env = dict(settings.get('env') or {})
    current = env.get('ANTHROPIC_BASE_URL')
    if on and current is None:
        env['ANTHROPIC_BASE_URL'] = URL
    elif not on and current == URL:
        del env['ANTHROPIC_BASE_URL']
    else:
        return None  # already right, or the owner points Claude elsewhere
    if env:
        settings['env'] = env
    else:
        settings.pop('env', None)
    return settings


def codex_config(text, on):
    """Codex's config.toml routed through the pool (on) or not -> new text, or None when unchanged or not ours."""
    base = CODEX_BLOCK.sub('', '\n'.join(line for line in text.splitlines() if line != CODEX_LINE)).strip()
    if on:
        if re.search(r'^model_provider\s*=', base, re.M):
            return None  # the owner picked a provider of their own
        block = (
            f'# BEGIN agentlab-pool\n[model_providers.{PROVIDER}]\nname = "Account pool"\n'
            f'base_url = "{URL}/backend-api/codex"\nwire_api = "responses"\n# END agentlab-pool\n'
        )
        new = f'{CODEX_LINE}\n{base}\n\n{block}' if base else f'{CODEX_LINE}\n\n{block}'
    else:
        new = base + '\n' if base else ''
    if new.strip() == text.strip():
        return None
    tomllib.loads(new)  # never write a config Codex can't read
    return new


def t3_stored_key():
    """The management key T3 keeps for our source: it moves it to its secret store and masks it in settings.json."""
    name = base64.urlsafe_b64encode(T3_SOURCE.encode()).decode().rstrip('=')
    try:
        with open(os.path.join(T3_SECRETS, f'usage-limit-source-{name}.bin'), encoding='utf-8') as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return ''


def t3_settings(settings, on, key='', stored=''):
    """T3's settings with the pool as a usage source (its quota bars) or without it -> new or None.
    `stored`: the key T3 already holds for it (then its masked copy in settings.json counts as this key)."""
    settings = dict(settings or {})
    sources = dict(settings.get('usageLimitSources') or {})
    source = {'kind': 'cliproxy', 'label': 'Account pool', 'url': URL, 'managementKey': key, 'enabled': True}
    current = dict(sources.get(T3_SOURCE) or {})
    if current and stored and stored == key:
        current['managementKey'] = key
    if on and current != source:
        sources[T3_SOURCE] = source
    elif not on and T3_SOURCE in sources:
        del sources[T3_SOURCE]
    else:
        return None
    settings['usageLimitSources'] = sources
    return settings


def sync():
    """Bring the proxy and every client's config in line with the configured accounts."""
    with _sync_lock:
        config, changed = seed_config(_load(CONFIG))
        if changed:
            _write_json(CONFIG, config)
        accts = accounts(config)
        claude_on, codex_on = wanted(accts)
        _supervise(bool(accts))
        if _readable(CLAUDE_SETTINGS) and (new := claude_settings(_load(CLAUDE_SETTINGS), claude_on)) is not None:
            _write_json(CLAUDE_SETTINGS, new)
        try:
            with open(CODEX_CONFIG) as f:
                text = f.read()
        except OSError:
            text = ''
        try:
            if (new := codex_config(text, codex_on)) is not None:
                _write(CODEX_CONFIG, new)
        except tomllib.TOMLDecodeError:
            pass  # Codex's config is broken already; agent-config reports that at start
        if os.path.isdir(os.path.dirname(T3_SETTINGS)) and _readable(T3_SETTINGS):
            key = (config.get('proxy') or {}).get('apiKey', '')
            if (new := t3_settings(_load(T3_SETTINGS), bool(accts), key, t3_stored_key())) is not None:
                _write_json(T3_SETTINGS, new)


def _supervise(on):
    state = subprocess.run([*SUPERVISOR, 'status', 'pool'], capture_output=True, text=True, check=False).stdout
    running = 'RUNNING' in state or 'STARTING' in state
    if on != running:
        subprocess.run([*SUPERVISOR, 'start' if on else 'stop', 'pool'], capture_output=True, check=False)


# --- what the hub shows


def _window(label, ratio, reset_ms):
    if not isinstance(ratio, (int, float)):
        return None
    return {'label': label, 'used': round(ratio * 100, 1), 'resetsAt': reset_ms / 1000 if reset_ms else None}


def _row(a, current):
    q = a.get('quota') or {}
    windows = [
        _window('5 hours', q.get('unified5h'), q.get('unified5hReset')),
        _window('Week', q.get('unified7d'), q.get('unified7dReset')),
        _window('Fable week', q.get('unified7dFable'), q.get('unified7dFableReset')),
    ]
    err = a.get('errorReason') or {}
    problem = (err.get('detail') or 'Needs a new sign-in.') if a.get('status') == 'error' else ''
    return {
        'name': a.get('name', ''),
        'provider': provider(a),
        'disabled': bool(a.get('disabled')),
        'current': a.get('name') == current.get(a.get('provider')),
        'problem': problem,
        'resting': '' if problem or a.get('disabled') else str(a.get('unavailable') or ''),
        'windows': [w for w in windows if w],
    }


def _flow(key):
    scr = screen(key) if active(key) else ''
    return {
        'key': key,
        'name': FLOWS[key]['name'],
        'hint': FLOWS[key]['hint'],
        'mode': 'default',
        'signedIn': False,
        'detail': '',
        'active': active(key),
        'url': next((u.rstrip('.,)') for u in URL_RE.findall(scr)), ''),
        'code': '',
        'done': bool(DONE_RE.search(scr)),
        'screen': scr[-4000:],
    }


def state():
    """Accounts with their quota (live from the proxy, or from the config while it is down) and any sign-in."""
    flows = [_flow(k) for k in FLOWS]
    if any(f['done'] for f in flows):
        threading.Thread(target=sync, daemon=True).start()
    code, body = http(f'{URL}/teamclaude/status', timeout=5)
    try:
        status = json.loads(body) if code == 200 else None
    except ValueError:
        status = None
    if status:
        current = status.get('currentAccounts') or {}
        rows = [_row(a, current) for a in status.get('accounts') or [] if a.get('type', 'oauth') == 'oauth']
    else:
        rows = [{**a, 'current': False, 'problem': '', 'resting': '', 'windows': []} for a in accounts()]
    claude_on, codex_on = wanted(rows)
    return {
        'running': bool(status),
        'routes': {'claude': claude_on, 'codex': codex_on},
        'accounts': rows,
        'flows': flows,
    }


def act(action, target, text):
    """-> '' or a message; unknown actions raise ValueError."""
    if action == 'pool-add':
        if target not in FLOWS:
            raise ValueError('Unknown provider.')
        for other in FLOWS:
            stop_session(other)
        start_session(target, FLOWS[target]['login'])
        return ''
    if action in ('pool-send', 'pool-stop', 'pool-key'):
        if target not in FLOWS:
            raise ValueError('Unknown provider.')
        if action == 'pool-send':
            type_into(target, text('text'))
        elif action == 'pool-key':
            if text('key') in ('Enter', 'Up', 'Down', 'Escape'):
                tmux('send-keys', '-t', session(target), text('key'))
        else:
            stop_session(target)
            sync()
        return ''
    names = {a['name'] for a in accounts()}
    if target not in names:
        raise ValueError('Unknown account.')
    commands = {
        'pool-remove': f'agent-teamclaude remove {sh_quote(target)}',
        'pool-disable': f'agent-teamclaude disable {sh_quote(target)}',
        'pool-enable': f'agent-teamclaude enable {sh_quote(target)}',
        'pool-first': f'agent-teamclaude priority {sh_quote(target)} --first',
    }
    if action not in commands:
        raise ValueError('Unknown action.')
    rc, out = run(commands[action], timeout=60)
    sync()
    return '' if rc == 0 else f'TeamClaude refused: {out[-300:]}'
