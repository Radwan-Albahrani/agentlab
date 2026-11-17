# shellcheck shell=bash
# shellcheck disable=SC2016  # the installers run in a child bash (attempt ... bash -c), which expands them
# Home-volume CLI installers, sourced by the entrypoint (missing only) and agent-updater (everything).

# Global CLIs installed and kept on latest with Bun (in ~/.bun, bins in ~/.bun/bin), and the commands they provide.
BUN_TOOLS=(@openai/codex@latest cyrus-ai@latest @playwright/mcp@latest mcp-remote@latest eas-cli@latest
  @karpeleslab/teamclaude@latest)
BUN_COMMANDS=(codex cyrus playwright-mcp mcp-remote eas teamclaude)
BUN_BIN="${HOME}/.bun/bin"
# Their npm copies from before Bun, removed once the Bun ones are in.
OLD_NPM_PACKAGES=(@openai/codex cyrus-ai @playwright/mcp mcp-remote eas-cli @karpeleslab/teamclaude)
OLD_NPM_COMMANDS=(codex cyrus playwright-mcp mcp-remote mcp-remote-client eas teamclaude teamrouter)

log() { echo "[tools $(date +%T)] $*"; }

# Via $CURL_HOME/.curlrc these limits also cover curl inside vendor install scripts, so no download hangs (#18).
CURL_HOME_DIR="${HOME}/.cache/agentlab/curl"

write_curlrc() {
  mkdir -p "${CURL_HOME_DIR}"
  printf '%s\n' 'connect-timeout = 20' 'retry = 5' 'retry-all-errors' 'speed-limit = 1024' 'speed-time = 60' \
    >"${CURL_HOME_DIR}/.curlrc"
}

# attempt NAME SECONDS COMMAND...: up to three tries, each cut off after SECONDS.
attempt() {
  local name=$1 limit=$2 try rc
  shift 2
  for try in 1 2 3; do
    CURL_HOME="${CURL_HOME_DIR}" timeout --kill-after=10 "${limit}" "$@"
    rc=$?
    [ "${rc}" -eq 0 ] && return 0
    log "${name}: attempt ${try} failed (exit ${rc}$([ "${rc}" -eq 124 ] && echo ', stalled past its time limit'))"
    [ "${try}" -lt 3 ] && sleep "$((try * ${ATTEMPT_BACKOFF_S:-15}))"
  done
  return 1
}

install_t3() {
  attempt "T3 Code install" 600 bash -c 'set -o pipefail; curl -fsSL https://t3.codes/install.sh | sh >"${HOME}/logs/t3-install.log" 2>&1' \
    || log "T3 Code install FAILED"
}

install_herdr() {
  attempt "herdr install" 600 bash -c 'set -o pipefail; curl -fsSL https://herdr.dev/install.sh | sh >"${HOME}/logs/herdr-install.log" 2>&1' \
    || log "herdr install FAILED"
}

install_bun() {
  attempt "Bun install" 600 bash -c 'set -o pipefail; curl -fsSL https://bun.sh/install | bash >"${HOME}/logs/bun-install.log" 2>&1' \
    || log "Bun install FAILED"
}

# bun_tools VERB: install or update every Bun tool. Their install scripts (Cyrus's cloudflared download) are trusted,
# as npm would run them: we picked these packages.
bun_tools() {
  attempt "bun ${1}" 1200 bash -c '
    "${0}" add -g "$@" >"${HOME}/logs/bun-tools.log" 2>&1 || exit
    "${0}" pm -g trust --all >>"${HOME}/logs/bun-tools.log" 2>&1 || true' "${BUN_BIN}/bun" "${BUN_TOOLS[@]}" \
    || log "bun ${1} failed (see ~/logs/bun-tools.log)"
}

missing_bun_tools() {
  local cmd
  for cmd in "${BUN_COMMANDS[@]}"; do [ -x "${BUN_BIN}/${cmd}" ] || return 0; done
  return 1
}

drop_old_npm_copies() {
  local root="${HOME}/.npm-global" pkg cmd
  for pkg in "${OLD_NPM_PACKAGES[@]}"; do [ -d "${root}/lib/node_modules/${pkg}" ] && rm -rf "${root}/lib/node_modules/${pkg}"; done
  for cmd in "${OLD_NPM_COMMANDS[@]}"; do [ -L "${root}/bin/${cmd}" ] && rm -f "${root}/bin/${cmd}"; done
  return 0
}

# Coolify briefly attaches its own network (#18): wait until AGENTLAB_WAIT_NETWORK is our only address.
container_addresses() { ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | sort; }

wait_for_final_network() {
  local want=${AGENTLAB_WAIT_NETWORK:-} limit=${NETWORK_WAIT_S:-300} waited=0 addrs
  [ -n "${want}" ] || return 0
  while :; do
    addrs=$(container_addresses)
    if [ "${addrs}" = "${want}" ]; then
      [ "${waited}" -gt 0 ] && log "network settled after ${waited}s"
      return 0
    fi
    if [ "${waited}" -ge "${limit}" ]; then
      log "still on more than its own network after ${limit}s (${addrs//$'\n'/ }); starting anyway"
      return 0
    fi
    [ "${waited}" -eq 0 ] && log "waiting until this container is on its own network only (${want})"
    sleep 2
    waited=$((waited + 2))
  done
}

install_missing_tools() {
  write_curlrc
  if ! command -v claude >/dev/null; then
    log "installing Claude Code"
    attempt "Claude Code install" 900 bash -c 'set -o pipefail; curl -fsSL https://claude.ai/install.sh | bash' \
      || log "Claude Code install FAILED"
  fi
  [ -x "${BUN_BIN}/bun" ] || install_bun
  if missing_bun_tools; then
    log "installing Codex, Cyrus, Playwright MCP, mcp-remote, EAS CLI, TeamClaude"
    bun_tools install
  fi
  missing_bun_tools || drop_old_npm_copies
  command -v t3 >/dev/null || install_t3
  command -v herdr >/dev/null || install_herdr
  if [[ ! -x /home/linuxbrew/.linuxbrew/bin/brew && -w /home/linuxbrew ]]; then
    log "installing Homebrew in the background"
    (CURL_HOME="${CURL_HOME_DIR}" NONINTERACTIVE=1 bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
      >"${HOME}/logs/brew-install.log" 2>&1 && echo "[done]" >>"${HOME}/logs/brew-install.log") &
  fi
}

# Everything to latest in place; a running T3 keeps its version until agent-updater restarts it.
update_tools() {
  write_curlrc
  log "updating Bun, Codex, Cyrus, Playwright MCP, mcp-remote, EAS CLI, TeamClaude, T3 Code, herdr, Claude Code"
  if [ -x "${BUN_BIN}/bun" ]; then
    attempt "bun upgrade" 600 bash -c '"${HOME}/.bun/bin/bun" upgrade >"${HOME}/logs/bun-upgrade.log" 2>&1' || log "bun upgrade failed"
  else
    install_bun
  fi
  bun_tools update
  missing_bun_tools || drop_old_npm_copies
  install_t3
  install_herdr
  command -v claude >/dev/null \
    && { attempt "claude update" 600 bash -c 'claude update >"${HOME}/logs/claude-update.log" 2>&1' || log "claude update failed"; }
  log "claude $(claude --version 2>/dev/null | head -1) | codex $(codex --version 2>/dev/null | head -1)" \
      "| t3 $(t3 --version 2>/dev/null | head -1) | herdr $(herdr --version 2>/dev/null | head -1) | eas $(eas --version 2>/dev/null | head -1)" \
      "| teamclaude $(teamclaude --version 2>/dev/null | head -1) | bun $("${BUN_BIN}/bun" --version 2>/dev/null)"
}
