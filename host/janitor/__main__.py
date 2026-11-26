"""Per-agent tidy: Docker leftovers (old unused volumes too), idle worktrees, rebuildable folders in scratch projects
left alone for a week, shared package files, and caches when storage is full; DRY=1 only lists."""

import contextlib
import json
import os
import shutil
import subprocess
import time

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


ASK_T3_S = 120


def chats_done(cid: str) -> dict[str, float | None] | None:
    """Per worktree path when its last chat finished (None while one is live), from the agent itself (agent-t3 in its
    image reads its T3 database); None when it couldn't answer or has no database yet."""
    try:
        p = subprocess.run(
            ['docker', 'exec', '-u', 'agent', cid, 'agent-t3', 'worktrees'],
            capture_output=True,
            text=True,
            check=False,
            timeout=ASK_T3_S,
        )
        got = json.loads(p.stdout) if p.returncode == 0 else None
    except (subprocess.TimeoutExpired, ValueError):
        return None
    if not isinstance(got, dict):
        return None
    out: dict[str, float | None] = {}
    for wt, since in got.items():
        if since is not None and (isinstance(since, bool) or not isinstance(since, int | float)):
            return None  # garbage
        out[wt] = since
    return out


def idle_worktrees(
    cid: str, root: str, now: float | None = None, hours: float = SETTLED_HOURS, days: float = ORPHAN_DAYS
) -> list[str]:
    """Worktrees (agent-side paths) whose chats have all been done long enough, per the agent's T3 database; none
    while the agent can't say."""
    now = now or time.time()
    done_since = chats_done(cid)
    if done_since is None:
        return []
    out = []
    base = f'{root}/workspace/worktrees'
    found = []  # T3 makes worktrees/<repo>/<name>; a chat's own `git worktree add` may make worktrees/<name>
    for repo in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        if os.path.isfile(f'{base}/{repo}/.git'):
            found.append(repo)
        elif os.path.isdir(f'{base}/{repo}'):
            found += [
                f'{repo}/{n}' for n in sorted(os.listdir(f'{base}/{repo}')) if os.path.isfile(f'{base}/{repo}/{n}/.git')
            ]
    for rel in found:
        wt = f'/workspace/worktrees/{rel}'
        if wt not in done_since:  # orphan: no chat knows it
            if now - os.path.getmtime(f'{base}/{rel}') > days * 86400:
                out.append(wt)
        elif (since := done_since[wt]) is not None and now - since > hours * 3600:
            out.append(wt)
    return out


def _newest(top: str, skip: tuple[str, ...] = REBUILDABLE) -> float:
    """The newest modification time under `top`, not looking inside rebuildable folders."""
    newest = os.path.getmtime(top)
    for d, dirs, files in os.walk(top):
        dirs[:] = [x for x in dirs if x not in skip and not os.path.islink(f'{d}/{x}')]
        for name in files:
            with contextlib.suppress(OSError):
                newest = max(newest, os.lstat(f'{d}/{name}').st_mtime)
    return newest


def _size(path: str) -> int:
    """Space removing `path` gives back: files linked elsewhere too (bun's store) free nothing."""
    total = 0
    for d, _, files in os.walk(path):
        for name in files:
            with contextlib.suppress(OSError):
                st = os.lstat(f'{d}/{name}')
                total += st.st_blocks * 512 if st.st_nlink == 1 else 0
    return total


def stale_builds(root: str, now: float | None = None, days: float = SCRATCH_DAYS, depth: int = 4) -> list[str]:
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


def clear_builds(root: str) -> tuple[list[str], int]:
    """(removed, bytes) for stale_builds; DRY only counts."""
    paths, freed = stale_builds(root), 0
    for p in paths:
        freed += _size(p)
        if not DRY:
            shutil.rmtree(p, ignore_errors=True)
    return paths, freed


def _run(cmd: list[str], stdin: str | None = None) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, input=stdin, check=False, timeout=1800)
    return (p.stdout + p.stderr).strip()


def container(data: str, agent_id: str) -> str | None:
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


def used(path: str) -> tuple[int, int]:
    s = os.statvfs(path)
    return (s.f_blocks - s.f_bfree) * s.f_frsize, s.f_blocks * s.f_frsize


def tidy(data: str, agent: cluster.Agent) -> tuple[list[str], int]:
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
    trees = '\n'.join(idle_worktrees(cid, root, hours=0 if full else SETTLED_HOURS)) + '\n'  # filling: done is enough
    dry, notice = f'DRY={"1" if DRY else ""}', f'NOTICE_DAYS={NOTICE_DAYS}'
    out = _run(['docker', 'exec', '-i', '-e', dry, '-e', notice, '-u', 'agent', cid, 'agent-worktree-remove'], trees)
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


def trim(cfg: cluster.Cluster) -> list[str]:
    """Hand the blocks freed inside each disk image back to the host disk (the images are sparse files)."""
    units = sorted({a['storage_unit'] for a in cfg.get('agents') or [] if a.get('storage_unit')})
    out = []
    for unit in units:
        if os.path.ismount(unit) and not DRY:
            line = _run(['fstrim', '-v', unit]).strip()
            if line:
                out.append(line)
    return out


def main() -> None:
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
    main()
