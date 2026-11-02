"""`agentctl setup`: from a bare server to running agents in one command. It asks a few questions (or takes them as
flags), writes cluster.toml, then runs init, install, Cloudflare and apply in order, stopping only where a person
has to act (a token to paste, a login link to open) and carrying on from there when run again. An existing
cluster.toml is kept unless the answers change it, and then only after a yes (or --yes)."""

import json
import os
import re
import socket
import sys
import tomllib

from . import apply, cloudflare, config, doctor, init, install, secret
from .util import OUT, Failed, Needs, Plan, run, say, write_if_changed

REACH = {
    'me': 'just me, on my own network: plain ports over my tailnet or LAN, no sign-in page',
    'tailnet': 'several people on one tailnet: HTTPS by tailscale serve, the tailnet is the sign-in',
    'cloudflare': 'Cloudflare: a tunnel plus Cloudflare Access (Google, Microsoft or a code by email)',
    'tinyauth': 'Google sign-in on the server itself (public ports)',
}
FIRST_PORT, PORT_STEP, HUB_PORT = 7101, 10, 7190
TOOLS = ('t3', 'accounts', 'browser', 'terminal', 'files')


# ---------------------------------------------------------------- the machine


def machine_name():
    return socket.gethostname().split('.')[0].lower()


def tailnet_name():
    """This machine's MagicDNS name when Tailscale runs here, else ''."""
    cli = doctor.tailscale_cli()
    if not cli:
        return ''
    rc, out = run([cli, 'status', '--json'], check=False)
    try:
        return (json.loads(out).get('Self') or {}).get('DNSName', '').rstrip('.') if rc == 0 else ''
    except ValueError:
        return ''


def facts():
    return {
        'name': machine_name(),
        'tailnet': tailnet_name(),
        'kvm': os.path.exists('/dev/kvm'),
        'wsl': doctor._wsl(),
    }


# ---------------------------------------------------------------- answers


def parse_people(text):
    """'sara@example.com=2, omar@example.com' -> [('sara@example.com', 2), ('omar@example.com', 1)]."""
    out = []
    for part in re.split(r'[,\s]+', text.strip()):
        if not part:
            continue
        email, _, n = part.partition('=')
        if not config.EMAIL.match(email):
            raise Failed(f'{email!r} is not an email address')
        if n and not n.isdigit():
            raise Failed(f'{part!r}: the number of agents must be a whole number')
        out.append((email.lower(), int(n or 1)))
    return out


def agent_ids(people, names=None):
    """Agent ids from the people: their email's name, numbered when they have several."""
    if names:
        return [(people[0][0], n) for n in names]
    out, used = [], set()
    for email, count in people:
        base = re.sub(r'[^a-z0-9-]+', '-', email.split('@')[0].lower()).strip('-')[:24] or 'agent'
        if not base[0].isalpha():
            base = 'a-' + base
        for i in range(count):
            aid = base if i == 0 else f'{base}-{i + 1}'
            while aid in used or aid in config.RESERVED:
                aid += '-x'
            used.add(aid)
            out.append((email, aid))
    return out


class Asker:
    """Takes each answer from its flag, else asks at a terminal, else uses the default; collects what's missing."""

    def __init__(self, flags, interactive, ask=input):
        self.flags, self.interactive, self.ask = flags, interactive, ask
        self.missing = []

    def get(self, key, question, default=None, flag=None, check=None):
        value = self.flags.get(key)
        if value in (None, '', []) and self.interactive:
            shown = f' [{default}]' if default not in (None, '') else ''
            while True:
                value = self.ask(f'{question}{shown}: ').strip() or default
                try:
                    if check and value not in (None, ''):
                        check(value)
                    break
                except Failed as e:
                    print(f'  {e}', file=sys.stderr)
        if value in (None, '', []):
            value = default
        if value in (None, '', []):
            self.missing.append(f'--{(flag or key).replace("_", "-")}')
        elif check:
            check(value)
        return value

    def choose(self, key, question, options, default):
        if self.interactive and not self.flags.get(key):
            say(question)
            keys = list(options)
            for i, k in enumerate(keys, 1):
                say(f'  {i}. {options[k]}')
            while True:
                pick = self.ask(f'Choose 1-{len(keys)} [{keys.index(default) + 1}]: ').strip()
                if not pick:
                    return default
                if pick.isdigit() and 1 <= int(pick) <= len(keys):
                    return keys[int(pick) - 1]
                if pick in options:
                    return pick
        value = self.flags.get(key) or default
        if value not in options:
            raise Failed(f'--{key.replace("_", "-")} must be one of: {", ".join(options)}')
        return value

    def yes(self, question, default=True):
        if not self.interactive:
            return default
        reply = self.ask(f'{question} [{"Y/n" if default else "y/N"}]: ').strip().lower()
        return default if not reply else reply.startswith('y')


def answers(flags, asker, machine):
    """Every answer cluster.toml needs, from flags, questions and the machine's own facts."""
    a = {'reach': asker.choose('reach', 'How will you reach your agents?', REACH, flags.get('reach') or 'me')}
    reach = a['reach']
    a['admin'] = asker.get('admin', 'Your email (you are the admin)', check=_email)
    if reach == 'me':
        default_host = machine['tailnet'].split('.')[0] if machine['tailnet'] else machine['name']
        a['domain'] = asker.get('domain', 'The name you reach this machine by', default_host)
        names = asker.get('agents', 'Your agents (names, comma separated)', 'main', check=_names)
        a['agents'] = agent_ids([(a['admin'] or 'you@example.com', 1)], _split(names))
    else:
        if reach == 'tailnet':
            a['domain'] = asker.get('domain', "This machine's tailnet name", machine['tailnet'] or None)
            a['hub_domain'] = a['domain']
        else:
            a['domain'] = asker.get('domain', 'The address for the agents, e.g. agents.example.com')
            zone = '.'.join(str(a['domain'] or 'example.com').split('.')[1:]) or 'example.com'
            a['hub_domain'] = asker.get('hub_domain', 'The address for the dashboard', f'agents-hub.{zone}')
            if reach == 'tinyauth':
                a['tinyauth_domain'] = asker.get(
                    'tinyauth_domain', 'The address for the sign-in page', f'agents-auth.{zone}'
                )
            a['allow_domains'] = _split(
                asker.get('allow_domains', 'Let everyone with an email at these domains sign in (optional)', '-')
            )
        people = asker.get(
            'people',
            'Who gets agents? emails, "=N" for more than one (e.g. sara@example.com=2, omar@example.com)',
            f'{a["admin"]}' if a['admin'] else None,
            check=parse_people,
        )
        a['agents'] = agent_ids(parse_people(people)) if people else []
    owners = {email for email, _ in a['agents']}
    a['storage'] = asker.choose(
        'storage',
        'Disk space:',
        {
            'shared': 'one pool for everyone (simplest)',
            'per-person': "a capped disk per person (one can't fill it for all)",
        },
        'per-person' if len(owners) > 1 else 'shared',
    )
    a['android'] = flags.get('android')
    if a['android'] is None:
        a['android'] = machine['kvm'] and asker.yes('Add the Android emulator (needs about 5 GB)?', machine['kvm'])
    a['deploy'] = flags.get('deploy') or 'compose'
    a['isolation'] = flags.get('isolation') or ('unconfined' if machine['wsl'] else 'sysbox')
    a['name'] = flags.get('name') or machine['name']
    a['tailscale'] = bool(machine['tailnet'])
    return a


def _email(v):
    if not config.EMAIL.match(str(v)):
        raise Failed(f'{v!r} is not an email address')


def _names(v):
    for n in _split(v):
        if not config.ID.match(n) or n in config.RESERVED:
            raise Failed(f'{n!r}: use lowercase letters, digits and dashes')


def _split(v):
    if isinstance(v, list):
        return v
    return [x for x in re.split(r'[,\s]+', str(v or '')) if x and x != '-']


# ---------------------------------------------------------------- cluster.toml


def toml_text(a):
    """cluster.toml for these answers: only what differs from the defaults, with a word on each choice."""
    q = json.dumps
    lines = ['# Written by `agentctl setup`. Change anything, then run `agentctl apply`.', '', '[cluster]']
    lines.append(f'name = {q(a["name"])}')
    lines.append(f'domain = {q(a["domain"])}')
    if a.get('hub_domain') and a['reach'] != 'me':
        lines.append(f'hub_domain = {q(a["hub_domain"])}')
    if a['reach'] == 'me':
        # the dashboard is reached on its own port; without Tailscale the name only has to differ from the domain
        lines.append(f'hub_domain = {q(a["domain"] if a["tailscale"] else "agentlab-hub")}')
        lines.append('publish_address = "0.0.0.0"          # the tools listen on these ports on your network')
    if a['deploy'] != 'compose':
        lines.append(f'deploy = {q(a["deploy"])}')
    if a['isolation'] != 'sysbox':
        lines.append(
            f'isolation = {q(a["isolation"])}'
            + ('   # Sysbox needs a regular Linux host' if a['isolation'] == 'unconfined' else '')
        )
    mode = {'me': 'tailscale' if a['tailscale'] else 'none', 'tailnet': 'tailscale'}.get(a['reach'], a['reach'])
    mode = 'cloudflare-access' if mode == 'cloudflare' else mode
    lines += ['', '[auth]', f'mode = {q(mode)}', f'admins = [{q(a["admin"])}]']
    if a.get('allow_domains'):
        lines.append(f'allow_domains = {q(a["allow_domains"])}')
    if mode == 'tinyauth':
        lines += ['', '[auth.tinyauth]', f'domain = {q(a["tinyauth_domain"])}']
    if a['storage'] != 'shared':
        lines += ['', '[storage]', f'mode = {q(a["storage"])}']
    if a['android']:
        lines += ['', '[android]', 'enabled = true']
    if a['reach'] == 'me':
        lines += [
            '',
            '[hub]',
            f'publish = {HUB_PORT}                       # the dashboard: http://{a["domain"]}:{HUB_PORT}',
        ]
    for n, (email, aid) in enumerate(a['agents']):
        lines += ['', '[[agents]]', f'id = {q(aid)}', f'owner = {q(email)}']
        if a['reach'] == 'me':
            base = FIRST_PORT + n * PORT_STEP
            lines.append('[agents.publish]')
            lines += [f'{tool} = {base + i}' for i, tool in enumerate(TOOLS)]
    return '\n'.join(lines) + '\n'


def summary(a):
    reach = REACH[a['reach']]
    people = sorted({e for e, _ in a['agents']})
    return [
        f'reach: {reach}',
        f'address: {a["domain"]}'
        + (f', dashboard {a["hub_domain"]}' if a.get('hub_domain') and a['reach'] != 'me' else ''),
        f'agents: {", ".join(i for _, i in a["agents"])} for {", ".join(people)}',
        f'storage: {a["storage"]}; Android: {"yes" if a["android"] else "no"}; isolation: {a["isolation"]}',
    ]


def write_config(path, text, asker, force):
    """True when cluster.toml was written. An existing one with other content is replaced only after a yes; the
    old one is kept next to it."""
    try:
        with open(path) as f:
            old = f.read()
    except FileNotFoundError:
        old = None
    if old == text:
        say(f'{path} already matches')
        return False
    if old is not None:
        if not (force or asker.yes(f'Replace {path}? (the current one is kept as {path}.before-setup)', False)):
            raise Needs(f'{path} already exists and differs: re-run with --yes to replace it, or edit it directly')
        write_if_changed(path + '.before-setup', old, mode=0o640)
    write_if_changed(path, text, mode=0o640)
    say(f'wrote {path}')
    return True


# ---------------------------------------------------------------- the run


def needed_secrets(cfg):
    """Secrets this cluster can't run without that aren't saved yet: [(name, why)]."""
    out = []
    if cfg['auth']['mode'] == 'cloudflare-access' or cfg['auth']['ingress'] == 'cloudflared':
        out.append(
            (
                'cloudflare-api',
                'a Cloudflare API token (My Profile → API Tokens → Create Token → Custom) with '
                + '; '.join(cloudflare.PERMISSIONS.values()),
            )
        )
    if cfg['auth']['mode'] == 'tinyauth':
        why = f'a Google OAuth client (redirect https://{cfg["tinyauth"]["domain"]}/api/oauth/callback/google)'
        out += [('tinyauth-google-id', f'the client id of {why}'), ('tinyauth-google-secret', 'its client secret')]
    files = secret.known(cfg)
    return [(n, why) for n, why in out if not os.path.isfile(files[n][1])]


def gather_secrets(cfg, asker):
    for name, why in needed_secrets(cfg):
        if not asker.interactive:
            raise Needs(f'needed: {why}. Save it with `agentctl secret set {name}`, then run agentctl setup again')
        say(f'agentlab needs {why}.')
        secret.set_secret(cfg, name)


def until_done(step, asker, attempts=10):
    """Run a step; when it stops for a person (Needs), say what's needed and, at a terminal, wait and try again."""
    for _ in range(attempts):
        try:
            return step()
        except Needs as e:
            if not asker.interactive:
                raise
            say(f'\n{e}')
            asker.ask('Press Enter when that is done (Ctrl-C to stop; `agentctl setup` picks up from here later)')
    return step()


def setup(config_path, flags, ask=input, interactive=None, steps=None):
    interactive = (not OUT.json and sys.stdin.isatty()) if interactive is None else interactive
    asker = Asker(flags, interactive, ask)
    steps = steps or {
        'init': lambda: init.init(config_path),
        'install': lambda cfg: install.install(cfg, config_path),
        'cloudflare': lambda cfg: cloudflare.setup(cfg, Plan(False), config_path),
        'apply': lambda cfg: apply.apply(cfg, config_path, False, None, False),
    }
    keep = os.path.exists(config_path) and not _has_answers(flags)
    if keep and interactive:
        keep = asker.yes(f'Keep the configuration in {config_path}?', True)
    if keep:
        say(f'using {config_path}')
    else:
        a = answers(flags, asker, facts())
        if asker.missing:
            raise Needs('setup needs: ' + ', '.join(asker.missing) + ' (or run it at a terminal to be asked)')
        for line in summary(a):
            say(f'  {line}')
        text = toml_text(a)
        config.resolve(tomllib.loads(text))  # never write a config agentctl would refuse
        if flags.get('config_only'):
            write_config(config_path, text, asker, flags.get('yes'))
            return {'config': config_path}
        if interactive and not asker.yes('Set it up like this?', True):
            raise Failed('stopped; nothing was changed')
        write_config(config_path, text, asker, flags.get('yes'))
    steps['init']()
    cfg = config.load(config_path)
    gather_secrets(cfg, asker)
    until_done(lambda: steps['install'](cfg), asker)
    if cfg['auth']['mode'] == 'cloudflare-access' or cfg['auth']['ingress'] == 'cloudflared':
        until_done(lambda: steps['cloudflare'](cfg), asker)
        cfg = config.load(config_path)  # it wrote the team and the Access audience
    steps['apply'](cfg)
    return {'config': config_path, 'open': where(cfg)}


def _has_answers(flags):
    return any(flags.get(k) not in (None, '', [], False) for k in ('reach', 'admin', 'domain', 'people', 'agents'))


def where(cfg):
    """What to open next."""
    if cfg['hub']['publish']:
        hub = f'http://{cfg["domain"]}:{cfg["hub"]["publish"]}'
    elif cfg['auth']['mode'] == 'tailscale':
        hub = f'https://{cfg["hub_domain"]}:{cfg["auth"]["hub_port"]}'
    else:
        hub = f'https://{cfg["hub_domain"]}'
    say(f'\nDone. Open your dashboard at {hub} and sign in to Claude or Codex there.')
    return {'hub': hub}
