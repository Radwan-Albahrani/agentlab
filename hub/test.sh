#!/bin/bash
# Check, build and click through the hub, all in pinned containers (only Docker is needed on the machine).
# Usage: hub/test.sh <command>
#   check            backend: ruff + unit tests; web app: types, lint, format, unit tests, production build
#                    (FIX=1: autofix first)
#   build [tag]      check, then build agentlab/hub:<tag> (default: test)
#   instance start|stop   a throwaway hub on 127.0.0.1:7189 over the example data (tests/fixtures.py), with fake
#                    agents, sign-in off (auth.mode "none" + HUB_ALLOW_NONE) and no phone pushes
#   e2e [url]        Playwright click-through (default: the throwaway hub; SHOTS=<dir> saves screenshots)
#   all              build, start the throwaway hub, e2e, stop it
set -uo pipefail
HUB=$(cd "$(dirname "$0")" && pwd)
TAG=agentlab/hub
TEST_PORT=7189
AGENTS_PORT=7188
DATA=/tmp/agentlab-hub-test
PY=python:3.13.1-alpine
RUFF=ruff==0.15.22
BUN=oven/bun:1.4.4-alpine
BUN_GLIBC=oven/bun:1.4.4         # the same Bun for the Playwright image (glibc, not musl)
PLAYWRIGHT=mcr.microsoft.com/playwright:v1.49.1-noble

die() { echo "error: $*" >&2; exit 1; }

cmd_check() {
  docker run --rm -e FIX="${FIX:-}" -v "${HUB}/..:/repo:ro" -v "${HUB}:/repo/hub" -w /repo/hub "${PY}" sh -c "
    set -e
    pip install --quiet --disable-pip-version-check --root-user-action=ignore ${RUFF} >/dev/null
    if [ -n \"\$FIX\" ]; then ruff check --fix -q . ; ruff format -q . ; fi
    ruff check --output-format concise . && ruff format --check -q . && echo 'backend: ruff ok'
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests 2>&1 | tail -3" || return 1
  # Bun installs (always from the frozen bun.lock: FIX fixes code, never moves dependencies) and runs every tool.
  docker run --rm -e FIX="${FIX:-}" -v "${HUB}/web:/web" -v agentlab-hub-web-modules:/web/node_modules -w /web "${BUN}" sh -c '
    set -eo pipefail
    bun install --frozen-lockfile --silent
    if [ -n "$FIX" ]; then bun --bun eslint . --fix >/dev/null || true; bun --bun prettier --write . >/dev/null; fi
    bun --bun run check
    bun --bun vitest run --reporter=dot
    bun --bun vite build --logLevel warn
    rm -rf dist
    echo "web app: types, lint, format, tests, build ok"'
  local rc=$?
  rmdir "${HUB}/web/node_modules" 2>/dev/null || true   # the empty mount point Docker leaves for the volume
  return "${rc}"
}

# shellcheck disable=SC2120  # the tag is optional: `all` builds the default one
cmd_build() {
  cmd_check || return 1
  docker build -q -t "${TAG}:${1:-test}" "${HUB}" >/dev/null || return 1
  docker images "${TAG}:${1:-test}" --format '{{.Repository}}:{{.Tag}} {{.Size}}'
}

cmd_instance() {
  case "${1:-}" in
    start)
      cmd_instance stop >/dev/null
      docker run --rm -v "${HUB}/tests:/tests:ro" -v "${DATA%/*}:${DATA%/*}" "${PY}" python3 /tests/fixtures.py "${DATA}"
      docker run -d --name agentlab-hub-agents --network host -v "${HUB}/tests:/tests:ro" -v "${DATA}:/data" "${PY}" \
        python3 /tests/fake_agent.py "${AGENTS_PORT}" /data/watch >/dev/null
      docker run -d --name agentlab-hub-test --network host -e HUB_PORT=${TEST_PORT} -e HUB_ALLOW_NONE=1 \
        -e HUB_CONFIG=/data/cluster.json -e HUB_AGENT_URL="http://127.0.0.1:${AGENTS_PORT}/{id}" \
        -e WATCH_DIR=/data/watch -e RENDERED_DIR=/data/rendered -e COMPANIONS_DIR=/data/companions \
        -e SECRETS_DIR=/data/secrets -e NOTIFY_DATA=/data/data -e AGENTS_DIR=/data/agents -e NOTIFY_T3='/data/agents/{id}/home/.t3/userdata' \
        -v "${DATA}:/data" "${TAG}:test" >/dev/null || return 1
      for _ in $(seq 20); do curl -sf -o /dev/null "http://127.0.0.1:${TEST_PORT}/health" && break; sleep 0.5; done
      echo "throwaway hub on http://127.0.0.1:${TEST_PORT}" ;;
    stop)
      docker rm -f agentlab-hub-test agentlab-hub-agents >/dev/null 2>&1
      docker run --rm -v "${DATA%/*}:${DATA%/*}" "${PY}" rm -rf "${DATA}"   # the containers wrote it as root
      echo stopped ;;
    *) die "usage: test.sh instance start|stop" ;;
  esac
}

# shellcheck disable=SC2120  # the URL is optional: `all` tests the throwaway hub
cmd_e2e() {
  local base=${1:-http://127.0.0.1:${TEST_PORT}} rc
  # Playwright needs its own image (browsers and their libraries) and runs on Node; Bun installs its packages
  docker run --rm -v agentlab-hub-bun-bin:/out "${BUN_GLIBC}" cp /usr/local/bin/bun /out/bun
  docker run --rm --network host --ipc host -e BASE_URL="${base}" -e SHOTS="${SHOTS:+/shots}" \
    -v agentlab-hub-bun-bin:/opt/bun:ro -v "${HUB}/web/e2e:/e2e" -v agentlab-hub-e2e-modules:/e2e/node_modules \
    ${SHOTS:+-v "${SHOTS}:/shots"} -w /e2e "${PLAYWRIGHT}" \
    sh -c '/opt/bun/bun install --frozen-lockfile --silent && /opt/bun/bun x playwright test "$@"' _ "${@:2}"
  rc=$?
  rmdir "${HUB}/web/e2e/node_modules" 2>/dev/null || true
  return "${rc}"
}

cmd_all() {
  local rc
  cmd_build || die "build failed"
  cmd_instance start || die "the throwaway hub did not start"
  cmd_e2e; rc=$?
  cmd_instance stop >/dev/null
  return "${rc}"
}

cmd=${1:-}; shift || true
cmd=cmd_${cmd//-/_}
declare -F "${cmd}" >/dev/null || { sed -n '3,11p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
"${cmd}" "$@"
