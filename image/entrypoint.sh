#!/bin/bash
# Agent container start: install missing CLIs into the home volume, register the browser tool, run supervisord.
# Only missing tools are installed before start; agent-updater (a supervisord program) keeps them current in the
# background, so a restart never waits on ~1.4 GB of npm writes.
set -u

BROWSER_TOOL=/usr/local/bin/browser-mcp-lazy   # starts the real Playwright MCP on first use

# shellcheck source=tools.sh
. /etc/agent/tools.sh                         # install_missing_tools, the same installers agent-updater uses
log() { echo "[bootstrap $(date +%T)] $*"; }

register_browser_tool() {
  agent-config codex "${HOME}/.codex/config.toml" "${BROWSER_TOOL}" \
    || log "WARNING: ~/.codex/config.toml was left unchanged (it is not valid TOML); Codex may refuse to start"
  claude mcp remove playwright -s user >/dev/null 2>&1
  claude mcp add-json playwright "{\"type\":\"stdio\",\"command\":\"${BROWSER_TOOL}\",\"args\":[],\"env\":{\"DISPLAY\":\":99\"}}" \
    -s user >/dev/null 2>&1 || log "could not register the browser tool with Claude Code"
}

clear_stale_state() {
  rm -f "${HOME}"/.chrome-profile/Singleton{Lock,Socket,Cookie}    # no Chrome survives a restart
  rm -f "${HOME}"/.local/state/agent-throttle/pid-*                # throttle job markers; process ids start over
  # ~/.profile prepends ~/.local/bin and ~/.cargo/bin after profile.d; loading the env last keeps the shims first.
  grep -qx '. /etc/agent/load-env.sh' "${HOME}/.profile" 2>/dev/null || printf '\n. /etc/agent/load-env.sh\n' >>"${HOME}/.profile"
}

mkdir -p "${HOME}"/{.local/bin,.npm-global,logs,.codex,.chrome-profile,.agentlab/requests,.agentlab/results} /workspace
wait_for_final_network                                # Coolify: only once agentlab took it off Coolify's network
install_missing_tools
register_browser_tool
android=()
android-emulator available && android=(--android)   # tell the agents about the phone only if it can run
agent-config notes "${AGENT_ID:?set by the compose file}" "${android[@]}"
agent-config skills                                   # our skills (companion) for Claude Code and Codex
clear_stale_state
exec supervisord -n -c /etc/agent-supervisord.conf
