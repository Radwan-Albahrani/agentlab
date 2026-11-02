#!/bin/bash
# Agent container start: install missing CLIs into the home volume, register the browser tool, run supervisord.
# Only missing tools are installed before start; updates run daily in the background, so a restart never waits on
# ~1.4 GB of npm writes.
set -u

# mcp-remote lets Claude and Codex share connector OAuth.
NPM_TOOLS=(@openai/codex@latest cyrus-ai@latest @playwright/mcp@latest mcp-remote@latest)
BROWSER_TOOL=/usr/local/bin/browser-mcp-lazy   # starts the real Playwright MCP on first use
UPDATE_STAMP=${HOME}/.config/agent/tools-updated

log() { echo "[bootstrap $(date +%T)] $*"; }

install_t3() { curl -fsSL https://t3.codes/install.sh | sh >"${HOME}/logs/t3-install.log" 2>&1 || log "T3 Code install FAILED"; }

install_missing_tools() {
  if ! command -v claude >/dev/null; then                    # Claude Code updates itself after the first install
    log "installing Claude Code"
    curl -fsSL https://claude.ai/install.sh | bash || log "Claude Code install FAILED"
  fi
  if ! command -v codex >/dev/null || ! command -v mcp-remote >/dev/null; then
    log "installing Codex, Cyrus, Playwright MCP, mcp-remote"
    npm install -g "${NPM_TOOLS[@]}" >"${HOME}/logs/npm-update.log" 2>&1 || log "npm install failed (see ~/logs/npm-update.log)"
  fi
  command -v t3 >/dev/null || install_t3
  command -v herdr >/dev/null || curl -fsSL https://herdr.dev/install.sh | sh >"${HOME}/logs/herdr-install.log" 2>&1 \
    || log "herdr install FAILED"
  if [[ ! -x /home/linuxbrew/.linuxbrew/bin/brew && -w /home/linuxbrew ]]; then   # first start only, ~2 min
    log "installing Homebrew in the background"
    (NONINTERACTIVE=1 bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
      >"${HOME}/logs/brew-install.log" 2>&1 && echo "[done]" >>"${HOME}/logs/brew-install.log") &
  fi
}

update_tools() {                                             # newer versions are used from the next start
  sleep 120
  [[ -n "$(find "${UPDATE_STAMP}" -mmin -1200 2>/dev/null)" ]] && return
  log "updating Codex, Cyrus, Playwright MCP, mcp-remote, T3 Code (background)"
  nice -n 15 ionice -c3 npm install -g "${NPM_TOOLS[@]}" >"${HOME}/logs/npm-update.log" 2>&1 \
    || log "npm update failed (see ~/logs/npm-update.log); keeping installed versions"
  nice -n 15 ionice -c3 bash -c "$(declare -f install_t3 log); install_t3"
  mkdir -p "$(dirname "${UPDATE_STAMP}")" && touch "${UPDATE_STAMP}"
  log "claude $(claude --version 2>/dev/null | head -1) | codex $(codex --version 2>/dev/null | head -1)" \
      "| t3 $(t3 --version 2>/dev/null | head -1) | herdr $(herdr --version 2>/dev/null | head -1)"
}

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
install_missing_tools
register_browser_tool
android=()
android-emulator available && android=(--android)   # tell the agents about the phone only if it can run
agent-config notes "${AGENT_ID:?set by the compose file}" "${android[@]}"
agent-config skills                                   # our skills (companion) for Claude Code and Codex
clear_stale_state
(update_tools >>"${HOME}/logs/bootstrap-update.log" 2>&1 &)
exec supervisord -n -c /etc/agent-supervisord.conf
