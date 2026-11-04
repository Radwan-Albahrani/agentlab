# shellcheck shell=bash
# Sourced by install steps. Exit 2 = manual step needed; agentctl install reports it and carries on.
set -euo pipefail
changed() { echo "changed: $*"; }
ok() { echo "ok: $*"; }
manual() { echo "MANUAL: $*"; exit 2; }
have() { command -v "$1" >/dev/null 2>&1; }
pick_package() {
  local p
  ls /var/lib/apt/lists/*Packages >/dev/null 2>&1 || DEBIAN_FRONTEND=noninteractive apt-get update -qq
  for p in "$@"; do
    # captured, not piped: under pipefail `apt-cache … | grep -q` fails whenever grep stops reading first
    if grep -q 'Candidate: [^(]' <<<"$(apt-cache policy "${p}" 2>/dev/null)"; then
      echo "${p}"
      return 0
    fi
  done
  return 1
}

apt_install() {
  local missing=() p
  for p in "$@"; do dpkg -s "${p}" >/dev/null 2>&1 || missing+=("${p}"); done
  [ ${#missing[@]} -eq 0 ] && return 0
  DEBIAN_FRONTEND=noninteractive apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${missing[@]}" >/dev/null
  changed "installed ${missing[*]}"
}
