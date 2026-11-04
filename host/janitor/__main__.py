"""Per-agent tidy: Docker leftovers, idle worktrees, and package caches when storage is full; DRY=1 only lists."""

import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime

import cluster

SETTLED_HOURS = 12
ORPHAN_DAYS = 2
CACHES_AT = 75
NOTICE_DAYS = 7  # untouched this long, a worktree with unsaved work goes too (saved as a ref)
DRY = bool(os.environ.get('DRY'))

DOCKER_PRUNE = """docker info >/dev/null 2>&1 || exit 0
docker container prune -f --filter until=72h >/dev/null
docker image prune -af --filter until=72h | tail -1
docker builder prune -af --filter until=72h | tail -1
docker volume prune -f | tail -1"""

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

CLEAR_CACHES = """npm cache clean --force 2>/dev/null; command -v bun >/dev/null && bun pm cache rm >/dev/null 2>&1
command -v pnpm >/dev/null && (cd /workspace && pnpm store prune >/dev/null 2>&1)
command -v brew >/dev/null && brew cleanup -s >/dev/null 2>&1; true"""


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
    before = used(unit)[0]
    if not DRY:
        pruned = _run(['docker', 'exec', '-u', 'agent', cid, 'sh', '-c', DOCKER_PRUNE])
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
    u, size = used(unit)
    if not DRY and size and 100 * u / size >= CACHES_AT:
        _run(['docker', 'exec', '-u', 'agent', cid, 'bash', '-lc', CLEAR_CACHES])
        lines.append(f'{agent_id}: package caches cleared (its storage at {CACHES_AT} % or more)')
    return lines, max(0, before - used(unit)[0])


def main():
    cfg = cluster.load()
    data = cluster.data_dir(cfg)
    report, freed = [], 0
    for a in cfg.get('agents') or []:
        lines, gone = tidy(data, a)
        report += lines
        freed += gone
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
