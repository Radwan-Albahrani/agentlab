"""Per-agent tidy: Docker leftovers (old unused volumes too), idle worktrees, rebuildable folders in scratch projects
left alone for a week, shared package files, and caches when storage is full; DRY=1 only lists."""

import contextlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime

import cluster

from janitor.dedupe import dedupe

SETTLED_HOURS = 6
ORPHAN_DAYS = 2
CACHES_AT = 70
NOTICE_DAYS = 3  # untouched this long, a worktree with unsaved work goes too (saved as a ref)
SCRATCH_DAYS = 2  # untouched this long, a scratch project in the agent's home loses its rebuildable folders
REBUILDABLE = ('node_modules', 'venv', '.venv')
DRY = bool(os.environ.get('DRY'))

DOCKER_PRUNE = """docker info >/dev/null 2>&1 || exit 0
docker container prune -f --filter until=24h >/dev/null
docker image prune -af --filter "until=${IMAGES_AGE:-24h}" | tail -1
docker builder prune -af | tail -1
docker volume prune -f | tail -1
cut=$(( $(date +%s) - 86400 )) n=0
for v in $(docker volume ls -qf dangling=true); do
  t=$(date -d "$(docker volume inspect -f '{{.CreatedAt}}' "$v" 2>/dev/null)" +%s 2>/dev/null || echo "$cut")
  [ "$t" -lt "$cut" ] && docker volume rm "$v" >/dev/null 2>&1 && n=$((n + 1))
done
[ "$n" -eq 0 ] || echo "removed $n unused volumes older than a day"
true"""

# Runs as the agent with worktree paths on stdin; unsaved work is kept as refs/agentlab/removed/<name> before removal.
REMOVE_WORKTREES = r'''removed="" kept="" n=0 now=$(date +%s)
while read -r wt; do
  [ -e "${wt}/.git" ] || continue
  name=${wt#/workspace/worktrees/}
  main=$(dirname "$(git -C "${wt}" rev-parse --path-format=absolute --git-common-dir)")
  changes=$(git -C "${wt}" status --porcelain | grep -v node_modules)
  dirty=$(printf '%s' "${changes}" | grep -c .)
  unpushed=$(git -C "${wt}" rev-list --count HEAD --not --remotes)
  if [ "${dirty}" -eq 0 ] && [ "${unpushed}" -eq 0 ]; then
    if [ -n "${DRY}" ] || git -C "${main}" worktree remove "${wt}" 2>/dev/null; then removed+=" ${name}"; n=$((n + 1));
    else kept+=" ${name} (git refused)"; fi
    continue
  fi
  why=""
  [ "${dirty}" -gt 0 ] && why="${dirty} uncommitted"
  [ "${unpushed}" -gt 0 ] && why="${why:+${why}, }${unpushed} commits on no remote"
  last=$(git -C "${wt}" log -1 --format=%ct HEAD 2>/dev/null || echo 0)
  while read -r f; do
    [ -n "${f}" ] || continue
    t=$(stat -c %Y "${wt}/${f}" 2>/dev/null || echo 0)
    [ "${t}" -gt "${last}" ] && last=${t}
  done <<< "$(printf '%s\n' "${changes}" | cut -c4- | sed 's/.* -> //')"
  due=$((last + NOTICE_DAYS * 86400))
  if [ "${now}" -lt "${due}" ]; then kept+=" ${name} (${why}; removed $(date -d "@${due}" +%b-%d) if untouched)"; continue; fi
  ref="refs/agentlab/removed/${name//\//-}"
  if [ -n "${DRY}" ]; then removed+=" ${name} (${why}, untouched ${NOTICE_DAYS} days)"; n=$((n + 1)); continue; fi
  git -C "${wt}" add -A -- . ':!node_modules' 2>/dev/null
  snap=$(git -C "${wt}" stash create 2>/dev/null)
  if git -C "${main}" update-ref "${ref}" "${snap:-$(git -C "${wt}" rev-parse HEAD)}" \
     && git -C "${main}" worktree remove --force "${wt}" 2>/dev/null; then
    removed+=" ${name} (${why}, untouched ${NOTICE_DAYS} days; saved as ${ref})"; n=$((n + 1))
  else kept+=" ${name} (git refused)"; fi
done
[ -n "${DRY}" ] || for r in /workspace/*/; do [ -d "${r}.git" ] && git -C "${r}" worktree prune; done
echo "$([ -n "${DRY}" ] && echo "would remove" || echo removed) ${n} idle worktrees:${removed:- none}${kept:+; kept:${kept}}"'''

# Every run. Not bun's cache: its files are hardlinked into every node_modules, so removing it frees nothing and the
# next install would make full copies again.
CLEAR_CACHES = """npm cache clean --force 2>/dev/null
command -v pnpm >/dev/null && (cd /workspace && pnpm store prune >/dev/null 2>&1)
command -v brew >/dev/null && brew cleanup -s >/dev/null 2>&1
command -v pip >/dev/null && pip cache purge >/dev/null 2>&1
command -v uv >/dev/null && uv cache clean >/dev/null 2>&1
for b in ~/.cache/puppeteer/*/; do ls -dt "$b"*/ 2>/dev/null | tail -n +2 | xargs -r rm -rf; done
rm -rf ~/.cache/node-gyp ~/.cache/go-build; true"""

# Only when the agent's storage is filling up: caches that cost a download to bring back.
CLEAR_MORE = """rm -rf ~/.cache/huggingface ~/.cache/dotslash ~/.cache/ms-playwright ~/.cache/puppeteer
command -v cargo >/dev/null && rm -rf ~/.cargo/registry/cache; true"""


def _epoch(iso):
    return datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp() if iso else 0


def idle_worktrees(root, now=None, hours=SETTLED_HOURS, days=ORPHAN_DAYS):
    """Worktrees (agent-side paths) whose chats have all been done long enough, per the agent's T3 database."""
    now = now or time.time()
    db = f'{root}/home/.t3/userdata/statev2.sqlite'
    if not os.path.exists(db):
        return []
    con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    try:
        running = {
            r[0]
            for r in con.execute(
                'select distinct thread_id from orchestration_v2_projection_runs where completed_at is null'
            )
        }
        last_turn = dict(
            con.execute('select thread_id, max(completed_at) from orchestration_v2_projection_runs group by thread_id')
        )
        threads = con.execute('select thread_id, payload_json, deleted_at from orchestration_v2_projection_threads')
        done_since = {}  # worktree -> when its last chat finished; None while one is still live
        for tid, payload, deleted in threads:
            d = json.loads(payload)
            wt = d.get('worktreePath')
            if not wt:
                continue
            settled, unsettled = _epoch(d.get('settledAt')), _epoch(d.get('unsettledAt'))
            # chats T3 never settles (delegate_task children) count from their last finished turn
            ended = (
                _epoch(deleted or d.get('deletedAt'))
                or _epoch(d.get('archivedAt'))
                or (settled if settled > unsettled else 0)
                or (_epoch(last_turn.get(tid) or d.get('updatedAt')) if not settled and not unsettled else 0)
            )
            if tid in running or not ended:
                done_since[wt] = None
            elif done_since.get(wt, 0) is not None:
                done_since[wt] = max(done_since.get(wt, 0), ended)
    finally:
        con.close()
    out = []
    base = f'{root}/workspace/worktrees'
    for repo in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        if not os.path.isdir(f'{base}/{repo}'):
            continue
        for name in sorted(os.listdir(f'{base}/{repo}')):
            on_host = f'{base}/{repo}/{name}'
            if not os.path.isfile(f'{on_host}/.git'):
                continue
            wt = f'/workspace/worktrees/{repo}/{name}'
            since = done_since.get(wt, 'orphan')
            if since == 'orphan':
                if now - os.path.getmtime(on_host) > days * 86400:
                    out.append(wt)
            elif since is not None and now - since > hours * 3600:
                out.append(wt)
    return out


def _newest(top, skip=REBUILDABLE):
    """The newest modification time under `top`, not looking inside rebuildable folders."""
    newest = os.path.getmtime(top)
    for d, dirs, files in os.walk(top):
        dirs[:] = [x for x in dirs if x not in skip and not os.path.islink(f'{d}/{x}')]
        for name in files:
            with contextlib.suppress(OSError):
                newest = max(newest, os.lstat(f'{d}/{name}').st_mtime)
    return newest


def _size(path):
    """Space removing `path` gives back: files linked elsewhere too (bun's store) free nothing."""
    total = 0
    for d, _, files in os.walk(path):
        for name in files:
            with contextlib.suppress(OSError):
                st = os.lstat(f'{d}/{name}')
                total += st.st_blocks * 512 if st.st_nlink == 1 else 0
    return total


def stale_builds(root, now=None, days=SCRATCH_DAYS, depth=4):
    """Rebuildable folders (node_modules, venv) in the agent's home scratch projects nobody touched for `days`."""
    now = now or time.time()
    home, out = f'{root}/home', []
    for name in sorted(os.listdir(home)) if os.path.isdir(home) else []:
        top = f'{home}/{name}'
        if name.startswith('.') or os.path.islink(top) or not os.path.isdir(top):
            continue
        found = []
        for d, dirs, _ in os.walk(top):
            if d[len(top) :].count('/') >= depth:
                dirs[:] = []
                continue
            found += [f'{d}/{x}' for x in dirs if x in REBUILDABLE and not os.path.islink(f'{d}/{x}')]
            dirs[:] = [x for x in dirs if x not in REBUILDABLE and x != '.git']
        if found and now - _newest(top) > days * 86400:
            out += found
    return out


def clear_builds(root):
    """(removed, bytes) for stale_builds; DRY only counts."""
    paths, freed = stale_builds(root), 0
    for p in paths:
        freed += _size(p)
        if not DRY:
            shutil.rmtree(p, ignore_errors=True)
    return paths, freed


def _run(cmd, stdin=None):
    p = subprocess.run(cmd, capture_output=True, text=True, input=stdin, check=False, timeout=1800)
    return (p.stdout + p.stderr).strip()


def container(data, agent_id):
    """The running agent container; under Coolify its project label is the service uuid."""
    stack = f'agentlab-agent-{agent_id}'
    try:
        with open(f'{data}/rendered/compose/{stack}/.coolify-service-uuid') as f:
            project = f.read().strip() or stack
    except OSError:
        project = stack
    ids = _run(
        [
            'docker',
            'ps',
            '-q',
            '--filter',
            f'label=com.docker.compose.project={project}',
            '--filter',
            'label=com.docker.compose.service=agent',
        ]
    ).split()
    return ids[0] if ids else None


def used(path):
    s = os.statvfs(path)
    return (s.f_blocks - s.f_bfree) * s.f_frsize, s.f_blocks * s.f_frsize


def tidy(data, agent):
    agent_id, root = agent['id'], agent['path']
    unit = agent.get('storage_unit') or root
    cid = container(data, agent_id)
    if not cid or not os.path.isdir(root) or (agent.get('storage_unit') and not os.path.ismount(unit)):
        return [], 0
    lines = []
    before, size = used(unit)
    full = bool(size) and 100 * before / size >= CACHES_AT  # filling up: unused images of any age, more caches
    if not DRY:
        age = ['-e', 'IMAGES_AGE=1h'] if full else []
        pruned = _run(['docker', 'exec', *age, '-u', 'agent', cid, 'sh', '-c', DOCKER_PRUNE])
        lines += [f'{agent_id}: {line}' for line in pruned.splitlines() if line.strip()]
    trees = '\n'.join(idle_worktrees(root)) + '\n'
    out = _run(
        [
            'docker',
            'exec',
            '-i',
            '-e',
            f'DRY={"1" if DRY else ""}',
            '-e',
            f'NOTICE_DAYS={NOTICE_DAYS}',
            '-u',
            'agent',
            cid,
            'bash',
            '-c',
            REMOVE_WORKTREES,
        ],
        stdin=trees,
    )
    lines.append(f'{agent_id}: {out.splitlines()[-1] if out else "no worktrees"}')
    gone, freed = clear_builds(root)
    if gone:
        folders = sorted({os.path.relpath(g, f'{root}/home').split('/')[0] for g in gone})
        lines.append(
            f'{agent_id}: {"would remove" if DRY else "removed"} {len(gone)} node_modules/venv folders'
            f' ({freed / 1e9:.1f} GB) in scratch folders untouched {SCRATCH_DAYS} days: {", ".join(folders)}'
        )
    n, saved = dedupe(f'{root}/workspace', dry=DRY)
    if n:
        lines.append(
            f'{agent_id}: {"would share" if DRY else "shared"} {n} identical package files ({saved / 1e9:.1f} GB)'
        )
    if not DRY:
        _run(['docker', 'exec', '-u', 'agent', cid, 'bash', '-lc', CLEAR_CACHES + ('\n' + CLEAR_MORE if full else '')])
        lines.append(
            f'{agent_id}: package caches cleared'
            + (f', downloaded browsers and models too (its storage at {CACHES_AT} % or more)' if full else '')
        )
    return lines, max(0, before - used(unit)[0])


def trim(cfg):
    """Hand the blocks freed inside each disk image back to the host disk (the images are sparse files)."""
    units = sorted({a['storage_unit'] for a in cfg.get('agents') or [] if a.get('storage_unit')})
    out = []
    for unit in units:
        if os.path.ismount(unit) and not DRY:
            line = _run(['fstrim', '-v', unit]).strip()
            if line:
                out.append(line)
    return out


def main():
    cfg = cluster.load()
    data = cluster.data_dir(cfg)
    report, freed = [], 0
    for a in cfg.get('agents') or []:
        lines, gone = tidy(data, a)
        report += lines
        freed += gone
    report += trim(cfg)
    print('\n'.join(report))
    if DRY:
        return
    event = {
        'at': time.time(),
        'kind': 'cleanup',
        'ok': True,
        'title': f'Cleanup freed {freed / 1e9:.1f} GB' if freed >= 5e7 else 'Cleanup: nothing to free',
        'detail': ' · '.join(report)[:600],
    }
    os.makedirs(f'{data}/hub/watch', exist_ok=True)
    with open(f'{data}/hub/watch/events.jsonl', 'a') as f:
        f.write(json.dumps(event) + '\n')


if __name__ == '__main__':
    sys.exit(main())
