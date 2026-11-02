"""agentctl: make one Linux server a private cluster of AI coding agents, from /etc/agentlab/cluster.toml.
Run any command with --json for machine-readable output. Exit codes: 0 done, 1 failed, 2 needs --yes, sudo or a
manual step. Only `setup` (at a terminal) and `secret set` (a hidden prompt) ever ask anything; commands that change
the host re-run themselves through sudo."""

import argparse
import json
import os
import sys

from . import (
    agents,
    apply,
    backup,
    cloudflare,
    companions,
    config,
    doctor,
    images,
    init,
    install,
    privileges,
    secret,
    setup,
    status,
    update,
)
from .util import NEEDS, OK, OUT, Failed, Plan, say, warn


def parser():
    p = argparse.ArgumentParser(prog='agentctl', description=__doc__.split('\n')[0])
    p.add_argument('--config', default=config.DEFAULT_PATH, help=f'cluster.toml (default {config.DEFAULT_PATH})')
    p.add_argument('--json', action='store_true', help='machine-readable output on stdout')
    sub = p.add_subparsers(dest='cmd', required=True)
    st = sub.add_parser('setup', help='guided setup: asks a few questions, then installs and starts everything')
    st.add_argument('--reach', choices=list(setup.REACH), help='how people reach the agents')
    st.add_argument('--no-pull', action='store_true', help="don't fetch the latest agentlab first")
    st.add_argument('--pulled', action='store_true', help=argparse.SUPPRESS)  # the re-run after a pull
    st.add_argument('--admin', help='your email (the admin)')
    st.add_argument('--domain', help='the address of the agents (a machine name on your own network)')
    st.add_argument('--hub-domain', help='the address of the dashboard (cloudflare, tinyauth)')
    st.add_argument('--tinyauth-domain', help='the address of the sign-in page (tinyauth)')
    st.add_argument('--people', help='who gets agents: "sara@example.com=2, omar@example.com"')
    st.add_argument('--agents', help='just me: your agents\' names, e.g. "work, personal"')
    st.add_argument('--allow-domains', help='also let everyone at these email domains sign in')
    st.add_argument('--storage', choices=['shared', 'per-person'])
    st.add_argument('--android', action=argparse.BooleanOptionalAction, default=None)
    st.add_argument('--deploy', choices=['compose', 'coolify'])
    st.add_argument('--isolation', choices=['sysbox', 'unconfined'])
    st.add_argument('--name', help='a short name for this cluster (default: the machine name)')
    st.add_argument('--yes', action='store_true', help='replace an existing cluster.toml with the new answers')
    st.add_argument('--config-only', action='store_true', help='write cluster.toml and stop')
    se = sub.add_parser('secret', help='save a secret where agentlab reads it').add_subparsers(
        dest='action', required=True
    )
    ss = se.add_parser('set', help='save a secret from stdin (hidden prompt at a terminal)')
    ss.add_argument('name', help='e.g. cloudflare-api, coolify, tailscale-authkey, companion/<name>/bot-token.txt')
    se.add_parser('list', help='the secrets this cluster uses and whether each is saved')
    sub.add_parser('init', help='first command on a new server: agentctl on PATH, the agentlab group, a starter config')
    sub.add_parser('doctor', help='check the host and the config; every problem comes with its fix')
    i = sub.add_parser('install', help='one-time host setup (Docker, Sysbox, cloudflared, Coolify, KVM, units)')
    i.add_argument('--only', nargs='+', metavar='STEP', help='run only these steps (e.g. units firewall)')
    i.add_argument('--skip-images', action='store_true', help='do not build or pull images')
    a = sub.add_parser('apply', help='render and deploy everything to match cluster.toml (idempotent)')
    a.add_argument('--dry-run', action='store_true', help='print the changes, make none')
    a.add_argument('--stack', help='redeploy this stack even if its file did not change')
    a.add_argument('--build', action='store_true', help='rebuild (or re-pull) the images first')
    a.add_argument('--force', action='store_true', help='redeploy every stack, even agents in the middle of a T3 turn')
    ag = sub.add_parser('agent', help='add, remove or list agents').add_subparsers(dest='action', required=True)
    add = ag.add_parser('add', help='add an agent for one person')
    add.add_argument('id')
    add.add_argument('email')
    add.add_argument('--dry-run', action='store_true')
    rm = ag.add_parser('remove', help='remove an agent (prints the plan; deleting data needs --yes)')
    rm.add_argument('id')
    rm.add_argument('--keep-data', action='store_true', help="keep the agent's disk image")
    rm.add_argument('--yes', action='store_true', help="confirm deleting the agent's data")
    rm.add_argument('--dry-run', action='store_true')
    ag.add_parser('list', help='every agent with its owner and limits')
    ad = ag.add_parser('adopt', help='mark an agent that already has AI sign-ins as onboarded')
    ad.add_argument('id')
    cf = sub.add_parser('cloudflare', help='Cloudflare tunnel, DNS and Access').add_subparsers(
        dest='action', required=True
    )
    cs = cf.add_parser('setup', help='create or update the tunnel, DNS records and the Access application')
    cs.add_argument('--dry-run', action='store_true')
    b = sub.add_parser('backup', help='backups of T3 chats, companion databases and the config')
    bs = b.add_subparsers(dest='action', required=True)
    bs.add_parser('run', help='back up now (the timer does this nightly)')
    bs.add_parser('list', help='backups on this server')
    br = bs.add_parser('restore', help="restore one agent's T3 databases from a backup")
    br.add_argument('date')
    br.add_argument('agent')
    br.add_argument('--yes', action='store_true', help="confirm overwriting the agent's current chats")
    im = sub.add_parser('images', help='build or pull the agentlab images').add_subparsers(dest='action', required=True)
    ib = im.add_parser('build', help='build images from this repo')
    ib.add_argument('names', nargs='*', metavar='NAME', help='any of: agent gate hub companion (default: all needed)')
    ip = im.add_parser('pull', help='pull images from [images] registry')
    ip.add_argument('names', nargs='*', metavar='NAME')
    co = sub.add_parser('companion', help='companions an agent creates for itself (the watcher runs these)')
    cos = co.add_subparsers(dest='action', required=True)
    cc = cos.add_parser('create', help='create a companion for an agent')
    cc.add_argument('agent')
    cc.add_argument('name')
    cc.add_argument('--display-name', default='')
    cc.add_argument('--kind', default='slack')
    cr = cos.add_parser('remove', help='remove an agent-created companion (its data is archived)')
    cr.add_argument('agent', help="the companion's agent ('-': whichever agent it belongs to)")
    cr.add_argument('name')
    up = sub.add_parser('update', help='pull agentlab, rebuild the images, apply; busy agents are waited for')
    up.add_argument('--scheduled', action='store_true', help='run by agentlab-update.timer (recorded as such)')
    up.add_argument('--pulled', action='store_true', help=argparse.SUPPRESS)  # the re-run after a pull
    sub.add_parser('status', help='agents, health, memory and disk at a glance')
    cf_ = sub.add_parser('config', help='print the resolved config, or `config edit` to change it')
    cf_.add_argument('action', nargs='?', choices=['show', 'edit'], default='show')
    return p


def dispatch(args):
    if args.cmd == 'agent' and args.action == 'add':
        return agents.add(args.config, args.id, args.email, args.dry_run)
    if args.cmd == 'agent' and args.action == 'remove':
        return agents.remove(args.config, args.id, args.keep_data, args.yes, args.dry_run)
    if args.cmd == 'companion' and args.action == 'create':
        return companions.create(args.config, args.agent, args.name, args.display_name, args.kind)
    if args.cmd == 'companion' and args.agent == '-':  # the hub's remove: the companion's own agent
        return companions.remove(args.config, companions.owner_of(config.load(args.config), args.name), args.name)
    if args.cmd == 'companion':
        return companions.remove(args.config, args.agent, args.name)
    if args.cmd == 'init':
        return init.init(args.config)
    if args.cmd == 'setup':
        if not (args.pulled or args.no_pull):
            fresh_code_then_rerun()
        keys = ('reach', 'admin', 'domain', 'hub_domain', 'tinyauth_domain', 'people', 'agents', 'allow_domains')
        flags = {k: getattr(args, k) for k in (*keys, 'storage', 'android', 'deploy', 'isolation', 'name')}
        flags.update(yes=args.yes, config_only=args.config_only)
        return setup.setup(args.config, flags)
    if args.cmd == 'config' and args.action == 'edit':
        return init.edit(args.config)
    cfg = config.load(args.config)
    if args.cmd == 'doctor':
        return run_doctor(cfg)
    if args.cmd == 'install':
        return install.install(cfg, args.config, args.only, args.skip_images)
    if args.cmd == 'apply':
        return apply.apply(cfg, args.config, args.dry_run, args.stack, args.build, force=args.force)
    if args.cmd == 'secret' and args.action == 'set':
        return secret.set_secret(cfg, args.name)
    if args.cmd == 'secret':
        rows = secret.listing(cfg)
        if not OUT.json:
            for r in rows:
                print(f'{"set    " if r["set"] else "missing"} {r["name"]}: {r["about"]}')
        return {'secrets': rows}
    if args.cmd == 'agent' and args.action == 'adopt':
        return agents.adopt(cfg, args.id)
    if args.cmd == 'agent':
        return {'agents': agents.listing(cfg)}
    if args.cmd == 'cloudflare':
        cloudflare.setup(cfg, Plan(args.dry_run), args.config)
        return {}
    if args.cmd == 'backup':
        if args.action == 'run':
            return backup.run(cfg, args.config)
        if args.action == 'list':
            return {'backups': backup.listing(cfg)}
        return backup.restore(cfg, args.date, args.agent, args.yes)
    if args.cmd == 'images':
        unknown = set(args.names) - set(images.SOURCES)
        if unknown:
            raise Failed(f'unknown image {", ".join(sorted(unknown))}: choose from {", ".join(images.SOURCES)}')
        if args.action == 'build':
            images.build(cfg, Plan(False), args.names or None, force=True)
        else:
            images.pull(cfg, Plan(False), args.names or None)
        return {}
    if args.cmd == 'update':
        argv = [a for a in sys.argv[1:] if a != '--pulled']
        return update.update(cfg, args.config, args.scheduled, pulled=True if args.pulled else None, argv=argv)
    if args.cmd == 'status':
        return status.show(cfg)
    if args.cmd == 'config':
        if not OUT.json:
            print(json.dumps(cfg, indent=2))
        return {'config': cfg}
    return {}


class DoctorFailed(Failed):
    def __init__(self, checks):
        super().__init__(f'{sum(ch["severity"] == "error" for ch in checks)} checks failed')
        self.result = {'checks': checks}


def fresh_code_then_rerun():
    """Setup is what people re-run after a fix, so it starts on the latest agentlab: fast-forward the checkout and
    re-run on the new code. Anything that stops the pull (not a checkout, local changes) is a note, not a failure."""
    try:
        before, after = update.pull('main')
    except Failed as e:
        warn(f'not fetching the latest agentlab: {e}')
        return
    if before != after:
        say(f'agentlab {before} -> {after}; continuing with the new code')
        os.execv(sys.executable, [sys.executable, *sys.argv, '--pulled'])


def run_doctor(cfg):
    """Checks print as a list for people; with --json they are the result, not messages."""
    checks = doctor.run_all(cfg)
    if not OUT.json:
        for ch in checks:
            mark = {'ok': 'ok  ', 'warning': 'warn', 'error': 'FAIL'}[ch['severity']]
            fix = f'\n       fix: {ch["fix"]}' if ch['fix'] else ''
            print(f'{mark} {ch["message"]}{fix}', flush=True)
    if any(ch['severity'] == 'error' for ch in checks):
        raise DoctorFailed(checks)
    return {'checks': checks}


def global_first(argv):
    """`agentctl doctor --json` and `agentctl --json doctor` both work: the global options move to the front, so an
    agent can append `--json` to any command."""
    front, rest, i = [], [], 0
    while i < len(argv):
        a = argv[i]
        if a == '--json' or a.startswith('--config='):
            front.append(a)
        elif a == '--config' and i + 1 < len(argv):
            front += argv[i : i + 2]
            i += 1
        else:
            rest.append(a)
        i += 1
    return front + rest


def main(argv=None):
    argv = global_first(sys.argv[1:] if argv is None else list(argv))
    args = parser().parse_args(argv)
    OUT.json = args.json
    result, code, error = {}, OK, ''
    try:
        privileges.elevate(args, argv)
        result = dispatch(args) or {}
    except Failed as e:
        code, error = e.code, str(e)
        result = getattr(e, 'result', {})
    except KeyboardInterrupt:
        code, error = 1, 'interrupted'
    if OUT.json:
        print(
            json.dumps(
                {
                    'ok': code == OK,
                    'exit': code,
                    'error': error,
                    'result': result,
                    'changes': OUT.changes,
                    'messages': OUT.messages,
                    'warnings': OUT.warnings,
                },
                indent=1,
            )
        )
    elif error:
        print(('needs action: ' if code == NEEDS else 'error: ') + error, file=sys.stderr)
    return code
