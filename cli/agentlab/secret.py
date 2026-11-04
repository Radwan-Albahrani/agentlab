"""`agentctl secret set <name>`: value from stdin only, never argv, written to the file agentlab reads."""

import getpass
import os
import re
import sys

from .util import AGENT_UID, OUT, Failed, need_root, say

# Must match host/watch/agent_requests.py SECRET_KEYS.
COMPANION_KEYS = (
    'owner.txt',
    'bot-token.txt',
    'app-token.txt',
    'user-token.txt',
    'github-app-id.txt',
    'github-app-key.pem',
    'work-tools.md',
)
COMPANION = re.compile(r'^companion/([a-z0-9][a-z0-9-]{0,28}[a-z0-9])/([a-z0-9.-]+)$')


def known(cfg):
    """{name: (what it is, file)} for the secrets this cluster uses."""
    data = cfg['data']
    out = {
        'cloudflare-api': ('the Cloudflare API token', cfg['cloudflare']['api_token_file']),
        'coolify': ('the Coolify API token', cfg['coolify']['token_file']),
        'tailscale-authkey': (
            'a Tailscale auth key (signs this machine in without opening a browser)',
            f'{data}/secrets/tailscale-authkey',
        ),
        'tinyauth-google-id': ("the Google OAuth client's id (tinyauth)", cfg['tinyauth']['google_client_id_file']),
        'tinyauth-google-secret': (
            "the Google OAuth client's secret (tinyauth)",
            cfg['tinyauth']['google_client_secret_file'],
        ),
    }
    for c in cfg['companions']:
        for key in COMPANION_KEYS:
            out[f'companion/{c["name"]}/{key}'] = (
                f"{c['display_name']}'s {key}",
                f'{data}/secrets/companions/{c["name"]}/{key}',
            )
    return out


def listing(cfg):
    return [
        {'name': name, 'about': about, 'set': os.path.isfile(path) and os.path.getsize(path) > 0}
        for name, (about, path) in known(cfg).items()
    ]


def read_value(about, stdin=None, prompt=getpass.getpass):
    stdin = stdin or sys.stdin
    at_terminal = stdin.isatty() and not OUT.json
    value = (prompt(f'Paste {about} (hidden), then Enter: ') if at_terminal else stdin.read()).strip()
    if not value:
        raise Failed('no value given: pipe it in, e.g. `agentctl secret set cloudflare-api < token.txt`')
    return value


def set_secret(cfg, name, stdin=None, prompt=getpass.getpass):
    need_root('agentctl secret set')
    secrets = known(cfg)
    if name not in secrets:
        m = COMPANION.match(name)
        hint = (
            f'{m.group(2)} is not a companion secret ({", ".join(COMPANION_KEYS)})'
            if m and m.group(2) not in COMPANION_KEYS
            else f'no companion {m.group(1)!r}'
            if m
            else 'known: '
            + ', '.join(n for n in secrets if not n.startswith('companion/'))
            + ', companion/<name>/<file>'
        )
        raise Failed(f'unknown secret {name!r}: {hint}')
    about, path = secrets[name]
    value = read_value(about, stdin, prompt)
    owner = AGENT_UID if name.startswith('companion/') else 0
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder, mode=0o700)
        os.chown(folder, owner, owner)
    with open(path + '.tmp', 'w') as f:
        f.write(value + '\n')
    os.chmod(path + '.tmp', 0o600)
    os.chown(path + '.tmp', owner, owner)
    os.replace(path + '.tmp', path)
    say(f'saved {about} to {path}')
    return {'name': name, 'path': path}
