"""agentctl: make one Linux server a private cluster of AI coding agents, from /etc/agentlab/cluster.toml.
Run any command with --json for machine-readable output. Exit codes: 0 done, 1 failed, 2 needs --yes or a manual
step. Nothing ever prompts."""

import argparse
import json
import sys

from . import agents, apply, backup, cloudflare, companions, config, doctor, images, install, status
from .util import NEEDS, OK, OUT, Failed, Plan


def parser():
    p = argparse.ArgumentParser(prog='agentctl', description=__doc__.split('\n')[0])
    p.add_argument('--config', default=config.DEFAULT_PATH, help=f'cluster.toml (default {config.DEFAULT_PATH})')
    p.add_argument('--json', action='store_true', help='machine-readable output on stdout')
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('doctor', help='check the host and the config; every problem comes with its fix')
    i = sub.add_parser('install', help='one-time host setup (Docker, Sysbox, cloudflared, Coolify, KVM, units)')
    i.add_argument('--only', nargs='+', metavar='STEP', help='run only these steps (e.g. units firewall)')
    i.add_argument('--skip-images', action='store_true', help='do not build or pull images')
    a = sub.add_parser('apply', help='render and deploy everything to match cluster.toml (idempotent)')
    a.add_argument('--dry-run', action='store_true', help='print the changes, make none')
    a.add_argument('--stack', help='redeploy this stack even if its file did not change')
    a.add_argument('--build', action='store_true', help='rebuild (or re-pull) the images first')
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
    ad = ag.add_parser('adopt', help='mark an agent with existing AI sign-ins as onboarded (migrations)')
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
    sub.add_parser('status', help='agents, health, memory and disk at a glance')
    sub.add_parser('config', help="print the resolved config (what cluster.json holds, plus agentctl's own keys)")
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
    cfg = config.load(args.config)
    if args.cmd == 'doctor':
        return run_doctor(cfg)
    if args.cmd == 'install':
        return install.install(cfg, args.config, args.only, args.skip_images)
    if args.cmd == 'apply':
        return apply.apply(cfg, args.config, args.dry_run, args.stack, args.build)
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
    args = parser().parse_args(global_first(sys.argv[1:] if argv is None else list(argv)))
    OUT.json = args.json
    result, code, error = {}, OK, ''
    try:
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
