"""Merge template changes into companion checkouts only when clean and conflict-free; git runs as the checkout's owner, never root."""

import contextlib
import datetime
import json
import os
import shutil
import stat
import subprocess
import tempfile
import time

from . import deploy, render
from .util import AGENT_UID, REPO, agent_folder, is_root, load_json, run, say, warn

BRANCH = 'template'
SOURCE = os.path.join(REPO, 'companion')
IGNORE = shutil.ignore_patterns('__pycache__', '*.pyc', '.pytest_cache', 'node_modules', '.git')
START_TIMEOUT_S = 300  # a changed requirements.txt means a venv install before the bot starts
SETTLE_S = 20  # running this long after the restart without failing counts as started
POLL_S = 3
AUTHOR = ['-c', 'user.name=agentlab', '-c', 'user.email=agentlab@localhost', '-c', 'commit.gpgsign=false']


def state_path(cfg):
    return os.path.join(cfg['data'], 'state', 'companions-template.json')


def _now():
    return datetime.datetime.now().astimezone().isoformat(timespec='seconds')


class Checkout:
    """git in one companion checkout as its owner; refuses a symlinked checkout or .git."""

    def __init__(self, path):
        for p in (path, os.path.join(path, '.git')):
            st = os.lstat(p)
            if not stat.S_ISDIR(st.st_mode):
                raise ValueError(f'{p} is not a plain folder')
        self.path = path
        self.uid = os.lstat(path).st_uid

    def _as_owner(self):
        if is_root() and self.uid != 0:
            return ['setpriv', f'--reuid={self.uid}', f'--regid={self.uid}', '--clear-groups', '--']
        return []

    def git(self, *args, check=True, env=None):
        full = dict(os.environ, HOME=self.path, GIT_CONFIG_NOSYSTEM='1', **(env or {}))
        return run([*self._as_owner(), 'git', '-C', self.path, *AUTHOR, *args], check=check, env=full)

    def rev(self, ref):
        rc, out = self.git('rev-parse', '--verify', '-q', ref, check=False)
        return out.strip() if rc == 0 else ''

    def ensure_branch(self):
        if self.rev(f'refs/heads/{BRANCH}'):
            return False
        root = self.git('rev-list', '--max-parents=0', 'HEAD')[1].split()[-1]
        self.git('branch', BRANCH, root)
        return True

    def snapshot_tree(self, source, objects=None):
        """Tree id of `source` as git would store it; with `objects`, new objects go only there (dry run)."""
        with tempfile.TemporaryDirectory(prefix='agentlab-template-') as tmp:
            work = os.path.join(tmp, 'tree')
            shutil.copytree(source, work, ignore=IGNORE, symlinks=True)
            env = {'GIT_INDEX_FILE': os.path.join(tmp, 'index'), 'GIT_WORK_TREE': work}
            if objects:
                env |= {'GIT_OBJECT_DIRECTORY': objects, 'GIT_ALTERNATE_OBJECT_DIRECTORIES': self._objects()}
            if self._as_owner():  # the owner must be able to read the copy and write the index
                _chown_tree(tmp, self.uid)
            self.git('add', '-A', env=env)
            return self.git('write-tree', env=env)[1].strip()

    def _objects(self):
        return os.path.join(self.path, '.git', 'objects')

    def commit_snapshot(self, tree, label):
        """A new commit on the template branch, without touching HEAD or the working tree."""
        tip = self.rev(f'refs/heads/{BRANCH}')
        new = self.git('commit-tree', tree, '-p', tip, '-m', f'agentlab template {label}')[1].strip()
        self.git('update-ref', f'refs/heads/{BRANCH}', new, tip)
        return tip, new

    def clean(self):
        return not self.git('status', '--porcelain', '--untracked-files=no')[1].strip()

    def merging(self):
        return self.rev('MERGE_HEAD') != ''


def _chown_tree(path, uid):
    """Hand a temp folder root made to the checkout's owner, who runs git on it."""
    for root, dirs, files in os.walk(path):
        for name in [root] + [os.path.join(root, n) for n in dirs + files]:
            os.lchown(name, uid, uid)


def version():
    rc, out = run(['git', '-C', REPO, 'describe', '--tags', '--always', '--dirty'], check=False)
    return out.strip() if rc == 0 and out.strip() else 'dev'


def short(sha):
    return sha[:7]


def status(cfg, comp):
    """The companion's status.json, read without following symlinks; None when unreadable."""
    agent = render.agent_of(cfg, comp)
    try:
        with agent_folder(f'{agent["path"]}/workspace', f'.companion/{comp["name"]}', create=False) as f:
            return f.read_json('status.json')
    except (FileNotFoundError, NotADirectoryError, ValueError, OSError):
        return None


def restart(cfg, comp):
    """Restart through Docker like the watcher does; False when the companion has no container (never deployed)."""
    ids = deploy.containers(cfg, f'agentlab-companion-{comp["name"]}', all_states=True)
    if not ids:
        return False
    run(['docker', 'restart', *ids], timeout=180)
    return True


def came_up(cfg, comp, since):
    """'' once the restarted companion is up (running and staying up, or cleanly 'not configured'), else why not."""
    deadline, running_since = time.time() + START_TIMEOUT_S, None
    last = None
    while time.time() < deadline:
        s = status(cfg, comp) or {}
        fresh = (s.get('updated') or 0) >= since
        state = s.get('state') if fresh else None
        last = s
        if state in ('failed', 'stopped'):
            return s.get('error') or f'it {state}'
        if state == 'not configured':
            return ''
        if state == 'running':
            running_since = running_since or time.time()
            if time.time() - running_since >= SETTLE_S:
                return ''
        else:
            running_since = None
        time.sleep(POLL_S)
    return f'not up after {START_TIMEOUT_S} s (last state: {(last or {}).get("state", "unknown")})'


def update_one(cfg, comp, dry=False):
    """-> {template_from, template_to, result, detail}; result: up-to-date, merged, conflict, skipped, reverted or would-update."""
    name = comp['name']
    path = render.companion_checkout(cfg, comp)
    out = {'template_from': '', 'template_to': '', 'result': 'skipped', 'detail': ''}
    try:
        co = Checkout(path)
    except FileNotFoundError:
        return out | {'detail': 'no checkout yet'}
    except ValueError as e:
        return out | {'detail': str(e)}
    source = SOURCE
    if dry:
        with tempfile.TemporaryDirectory(prefix='agentlab-objects-') as objects:
            if co._as_owner():
                _chown_tree(objects, co.uid)
            tree = co.snapshot_tree(source, objects=objects)
        tip = co.rev(f'refs/heads/{BRANCH}') or co.git('rev-list', '--max-parents=0', 'HEAD')[1].split()[-1]
        behind = co.rev(f'{tip}^{{tree}}') != tree or not _contains(co, tip)
        return out | {
            'template_from': short(tip),
            'result': 'would-update' if behind else 'up-to-date',
            'detail': 'template changes to merge' if behind else '',
        }
    if co.ensure_branch():
        say(f'  {name}: started its {BRANCH} branch at the seed commit')
    tree = co.snapshot_tree(source)
    tip = co.rev(f'refs/heads/{BRANCH}')
    if co.rev(f'{tip}^{{tree}}') != tree:
        old, tip = co.commit_snapshot(tree, version())
        say(f'  {name}: template snapshot {short(old)} -> {short(tip)}')
    frm = co.git('merge-base', 'HEAD', BRANCH, check=False)[1].strip() or tip
    out |= {'template_from': short(frm), 'template_to': short(tip)}
    if _contains(co, tip):
        return out | {'result': 'up-to-date'}
    if co.merging():
        return out | {'detail': 'a merge is in progress in the checkout'}
    if not co.clean():
        return out | {'detail': 'uncommitted changes in the checkout; merged on a later update once they are committed'}
    pre = co.rev('HEAD')
    rc, text = co.git(
        'merge',
        '--no-ff',
        '--no-edit',
        '-m',
        f'chore: merge agentlab template {short(frm)}..{short(tip)}',
        BRANCH,
        check=False,
    )
    kept = []
    if rc:
        conflicts = co.git('diff', '--name-only', '--diff-filter=U', check=False)[1].split()
        kept = _already_in_template(co, frm, pre, conflicts)
        if conflicts and kept == conflicts:
            for f in kept:
                co.git('checkout', '--theirs', '--', f)
                co.git('add', '--', f)
            rc, text = co.git('commit', '--no-edit', check=False)
    if rc:
        co.git('merge', '--abort', check=False)
        if co.rev('HEAD') != pre or not co.clean():
            warn(f'{name}: the checkout is not back at {short(pre)} after aborting the merge; look at {path}')
        files = ', '.join(conflicts) or text[-200:]
        return out | {
            'result': 'conflict',
            'detail': f'template update needs merging (conflicts in: {files})',
            'files': files,
        }
    merged = co.rev('HEAD')
    if kept:
        say(f"  {name}: kept the template version of {', '.join(kept)} (it already had this checkout's changes)")
    since = time.time()
    if not restart(cfg, comp):
        return out | {'result': 'merged', 'detail': f'merged as {short(merged)}; not running, nothing to restart'}
    why = came_up(cfg, comp, since)
    if not why:
        return out | {'result': 'merged', 'detail': f'merged as {short(merged)}; restarted and running'}
    # Undo exactly the merge made above, never anything the agent committed since.
    if co.rev('HEAD') == merged and co.rev(f'{merged}^1') == pre:
        co.git('reset', '--hard', pre)
        restart(cfg, comp)
        return out | {'result': 'reverted', 'detail': f'template update reverted: companion failed to start: {why}'}
    warn(f'{name}: failed to start after the template merge but HEAD moved since; left as it is')
    return out | {'result': 'merged', 'detail': f'merged as {short(merged)} but the companion failed to start: {why}'}


def _already_in_template(co, base, ours, files):
    """Conflicted files whose template version already holds every change the checkout made since `base`."""
    found = []
    with tempfile.TemporaryDirectory(prefix='agentlab-merge-') as tmp:
        for f in files:
            patch = co.git('diff', '-U0', '--no-color', base, ours, '--', f, check=False)[1]
            rc, theirs = co.git('show', f'{BRANCH}:{f}', check=False)
            if not patch or rc:
                continue
            target = os.path.join(tmp, 'a', f)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, 'w', newline='') as out:
                out.write(theirs + ('\n' if theirs and not theirs.endswith('\n') else ''))
            with open(os.path.join(tmp, 'patch'), 'w', newline='') as out:
                out.write(patch + '\n')
            # outside any repo, so nothing here runs the agent's code
            check = subprocess.run(
                ['git', 'apply', '-R', '--check', '--unidiff-zero', '-p1', '--directory=a', 'patch'],
                cwd=tmp,
                capture_output=True,
                check=False,
            )
            if check.returncode == 0:
                found.append(f)
    return found


def _contains(co, rev):
    return co.git('merge-base', '--is-ancestor', rev, 'HEAD', check=False)[0] == 0


MERGE_ASK = """agentlab's companion template has an update for {name} that conflicts with your own changes in: {files}.
Merge it in /workspace/companions/{name}: `git merge template`, then resolve each conflict so that your behaviour stays
and every template fix lands too. Where both sides fix the same thing, take the template's version, so later updates
merge cleanly. Then `companion test {name}`, commit, `companion restart {name}`, and check `companion status {name}`
and `companion logs {name}`. If a conflict needs a decision only the person can make, stop and ask them."""


def ask_agent(cfg, comp, files):
    """Start a chat in the companion's agent asking it to merge; True once started."""
    agent = render.agent_of(cfg, comp)
    ids = deploy.containers(cfg, f'agentlab-agent-{agent["id"]}', 'agent')
    if not ids:
        return False
    rc, out = run(
        [
            *('docker', 'exec', '-i', '-u', 'agent', '-w', '/workspace', ids[0], 't3', 'thread', 'start', '--json'),
            *('--title', f'Merge the {comp["name"]} template update', '/workspace', '-'),
        ],
        input_text=MERGE_ASK.format(name=comp['name'], files=files),
        check=False,
        timeout=120,
    )
    if rc:
        warn(f'{comp["name"]}: could not ask the {agent["id"]} agent to merge the template: {out[-200:]}')
    return rc == 0


def update_all(cfg, plan):
    results = {}
    before = {} if plan.dry else load_json(state_path(cfg), {}) or {}
    for comp in cfg['companions']:
        try:
            r = update_one(cfg, comp, dry=plan.dry)
        except Exception as e:
            r = {'template_from': '', 'template_to': '', 'result': 'skipped', 'detail': f'error: {e}'[-300:]}
        results[comp['name']] = r
        if plan.dry:
            if r['result'] == 'would-update':
                plan.do(f'merge the template into {comp["name"]} (from {r["template_from"]})')
            continue
        if r['result'] == 'conflict':
            # once per template version: the agent owns the checkout, so it does the merge
            asked = (before.get(comp['name']) or {}).get('asked_agent')
            if asked != r['template_to'] and ask_agent(cfg, comp, r.get('files') or 'see git status'):
                asked = r['template_to']
            if asked == r['template_to']:
                r['asked_agent'] = asked
                r['detail'] += f'; its agent was asked to merge it ({render.agent_of(cfg, comp)["id"]})'
        r.pop('files', None)
        r['at'] = _now()
        if r['result'] not in ('up-to-date',):
            say(f'  {comp["name"]}: template {r["result"]}{": " + r["detail"] if r["detail"] else ""}')
    if not plan.dry:
        _save(cfg, results)
    return results


def _save(cfg, results):
    path = state_path(cfg)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + '.tmp', 'w') as f:
        json.dump(results, f, indent=2)
    os.replace(path + '.tmp', path)
    for name, r in results.items():
        folder = os.path.join(cfg['data'], 'companions', name)
        if not os.path.isdir(folder):
            continue
        with contextlib.suppress(OSError):
            with open(os.path.join(folder, '.template.json.tmp'), 'w') as f:
                json.dump(r, f, indent=2)
            os.replace(os.path.join(folder, '.template.json.tmp'), os.path.join(folder, 'template.json'))
            if is_root():
                os.chown(os.path.join(folder, 'template.json'), AGENT_UID, AGENT_UID)


def summary(cfg):
    """Short status lines for companions whose template isn't simply up to date."""
    lines = []
    for name, r in (load_json(state_path(cfg), {}) or {}).items():
        if r.get('result') in (None, 'up-to-date'):
            continue
        lines.append(
            f'{name}: template {r["result"]} {r.get("template_from", "")}..{r.get("template_to", "")}'
            + (f' ({r["detail"]})' if r.get('detail') else '')
        )
    return lines
