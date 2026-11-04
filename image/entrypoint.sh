#!/bin/bash
# Agent container start: install only missing CLIs (agent-updater updates them), configure, run supervisord.
set -u

BROWSER_TOOL=/usr/local/bin/browser-mcp-lazy

# shellcheck source=tools.sh
. /etc/agent/tools.sh
log() { echo "[bootstrap $(date +%T)] $*"; }

register_browser_tool() {
  agent-config codex "${HOME}/.codex/config.toml" "${BROWSER_TOOL}" \
    || log "WARNING: ~/.codex/config.toml was left unchanged (it is not valid TOML); Codex may refuse to start"
  claude mcp remove playwright -s user >/dev/null 2>&1
  claude mcp add-json playwright "{\"type\":\"stdio\",\"command\":\"${BROWSER_TOOL}\",\"args\":[],\"env\":{\"DISPLAY\":\":99\"}}" \
    -s user >/dev/null 2>&1 || log "could not register the browser tool with Claude Code"
}

clear_stale_state() {
  rm -f "${HOME}"/.chrome-profile/Singleton{Lock,Socket,Cookie}
  rm -f "${HOME}"/.local/state/agent-throttle/pid-*
  # ~/.profile prepends tool folders after profile.d: loading the env last keeps the shims first.
  grep -qx '. /etc/agent/load-env.sh' "${HOME}/.profile" 2>/dev/null || printf '\n. /etc/agent/load-env.sh\n' >>"${HOME}/.profile"
}

mkdir -p "${HOME}"/{.local/bin,.npm-global,logs,.codex,.chrome-profile,.agentlab/requests,.agentlab/results} /workspace
wait_for_final_network
install_missing_tools
register_browser_tool
android=()
android-emulator available && android=(--android)
agent-config notes "${AGENT_ID:?set by the compose file}" "${android[@]}"
agent-config skills
clear_stale_state
exec supervisord -n -c /etc/agent-supervisord.conf
