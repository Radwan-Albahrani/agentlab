#!/bin/bash
# Lint and test every part of the repo in pinned containers, so only Docker is needed and every machine (and CI)
# checks with the same tools. Usage: scripts/check.sh [part ...]   parts: lint cli host gate companion image shell hub
# FIX=1 lets ruff fix and format first. The hub's own script also builds its web app (hub/test.sh check).
set -uo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
PY=python:3.12.8-slim
RUFF=ruff==0.15.22
MYPY=mypy==2.4.1
SHELLCHECK=koalaman/shellcheck-alpine:v0.10.0
failed=()

py() {  # py <name> <commands>: run in the Python image with the repo at /repo (writable only with FIX)
  local mode=ro
  [ -n "${FIX:-}" ] && [ "$1" = lint ] && mode=rw
  docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -e PIP_DISABLE_PIP_VERSION_CHECK=1 -e PIP_ROOT_USER_ACTION=ignore     -e RUFF_CACHE_DIR=/tmp/ruff-cache \
    -v "$REPO:/repo:$mode" -w /repo "$PY" bash -c "set -eo pipefail; $2" || failed+=("$1")
}

part_lint() {  # per part: each folder is its own import root (first-party modules differ)
  local fix=''
  [ -n "${FIX:-}" ] && fix='ruff check --fix -q . ; ruff format -q . ;'
  py lint "pip install -q $RUFF
    for d in cli host gate companion image hub; do
      (cd \$d && $fix ruff check --output-format concise . && ruff format --check -q .) || exit 1
    done
    echo 'ruff ok'"
  copies || failed+=(copies)
}
copies() {  # a schema each image needs, kept as exact copies of one source (each image builds from its own folder)
  local ok=0 pair
  for pair in image/t3schema.py:companion/t3schema.py image/t3schema.py:hub/notify/t3schema.py \
    companion/tables.py:hub/store/companion_tables.py; do
    cmp -s "$REPO/${pair%%:*}" "$REPO/${pair##*:}" || { echo "${pair##*:} differs from ${pair%%:*}: copy it over"; ok=1; }
  done
  return $ok
}
part_cli() {  # git for the companion template tests, which work on real repos; SQLAlchemy only builds test databases
  py cli 'apt-get update -qq >/dev/null && apt-get install -y -qq --no-install-recommends git >/dev/null
    pip install -q SQLAlchemy==2.1.9 '"$MYPY"'
    (cd cli && mypy --cache-dir /tmp/mypy)  # every function typed (cli/mypy.ini); the repo is read-only here
    cd cli && python -m unittest discover -s tests 2>&1 | tail -3'
}
part_host() {  # git for the janitor's worktree tests
  py host "apt-get update -qq >/dev/null && apt-get install -y -qq --no-install-recommends git >/dev/null
    pip install -q $MYPY && cd host && mypy --cache-dir /tmp/mypy && mypy --cache-dir /tmp/mypy --scripts-are-modules bin/agentlab-mount-storage
    python -m unittest discover -s tests 2>&1 | tail -3"
}
part_gate() { py gate 'cd gate && pip install -q -r requirements.txt && python -m unittest discover -s tests -t . 2>&1 | tail -3'; }
part_companion() {  # mypy first: every function in the bot is typed (companion/mypy.ini)
  py companion 'cd companion && pip install -q -r tests/requirements.txt && mypy --cache-dir /tmp/mypy  # the repo is read-only here
    python -m pytest -q -p no:cacheprovider tests 2>&1 | tail -3'
}
part_image() {  # gcc for the emulator's non-dumpable preload; mypy for the T3 database readers (image/mypy.ini)
  py image 'apt-get update -qq >/dev/null && apt-get install -y -qq --no-install-recommends gcc libc6-dev >/dev/null
    pip install -q pytest==8.3.4 SQLAlchemy==2.1.9 '"$MYPY"'
    (cd image && mypy --cache-dir /tmp/mypy && mypy --cache-dir /tmp/mypy agent-t3)
    python -m pytest -q -p no:cacheprovider image/tests 2>&1 | tail -3'
}
part_shell() {
  docker run --rm -v "$REPO:/repo:ro" -w /repo "$SHELLCHECK" sh -c \
    'shellcheck -x -P SCRIPTDIR host/install/*.sh scripts/check.sh hub/test.sh image/build.sh image/entrypoint.sh image/tools.sh image/adb \
       image/agent-terminal image/agent-dockerd image/agent-dockerd-root image/android-emulator image/browser-idle-reaper image/chrome-on-demand image/agent-teamclaude image/throttle/shim \
     && echo "shellcheck ok"' || failed+=(shell)
}
part_hub() { "$REPO/hub/test.sh" check || failed+=(hub); }

parts=("$@")
[ ${#parts[@]} -eq 0 ] && parts=(lint cli host gate companion image shell hub)
for p in "${parts[@]}"; do
  echo "== $p"
  "part_$p"
done
if [ ${#failed[@]} -gt 0 ]; then
  echo "FAILED: ${failed[*]}"
  exit 1
fi
echo "all checks passed"
