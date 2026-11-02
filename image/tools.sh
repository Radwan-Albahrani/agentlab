# shellcheck shell=bash
# The fast-moving CLIs (Claude Code, Codex, T3, herdr, ...) live in the home volume, not the image, so they can update
# without a rebuild. Sourced by the entrypoint (install what's missing before start) and by agent-updater (refresh
# everything in the background), so both always install the same things the same way.

# mcp-remote lets Claude and Codex share connector OAuth.
NPM_TOOLS=(@openai/codex@latest cyrus-ai@latest @playwright/mcp@latest mcp-remote@latest)

log() { echo "[tools $(date +%T)] $*"; }

install_t3() { curl -fsSL https://t3.codes/install.sh | sh >"${HOME}/logs/t3-install.log" 2>&1 || log "T3 Code install FAILED"; }

install_herdr() {
  curl -fsSL https://herdr.dev/install.sh | sh >"${HOME}/logs/herdr-install.log" 2>&1 || log "herdr install FAILED"
}

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
  command -v herdr >/dev/null || install_herdr
  if [[ ! -x /home/linuxbrew/.linuxbrew/bin/brew && -w /home/linuxbrew ]]; then   # first start only, ~2 min
    log "installing Homebrew in the background"
    (NONINTERACTIVE=1 bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
      >"${HOME}/logs/brew-install.log" 2>&1 && echo "[done]" >>"${HOME}/logs/brew-install.log") &
  fi
}

# Everything to its latest version in place. A running T3 server keeps its version until agent-updater restarts it
# while the agent is idle; the CLIs pick theirs up on their next run.
update_tools() {
  log "updating Codex, Cyrus, Playwright MCP, mcp-remote, T3 Code, herdr, Claude Code"
  npm install -g "${NPM_TOOLS[@]}" >"${HOME}/logs/npm-update.log" 2>&1 \
    || log "npm update failed (see ~/logs/npm-update.log); keeping installed versions"
  install_t3
  install_herdr
  command -v claude >/dev/null && { claude update >"${HOME}/logs/claude-update.log" 2>&1 || log "claude update failed"; }
  log "claude $(claude --version 2>/dev/null | head -1) | codex $(codex --version 2>/dev/null | head -1)" \
      "| t3 $(t3 --version 2>/dev/null | head -1) | herdr $(herdr --version 2>/dev/null | head -1)"
}
