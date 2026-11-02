# shellcheck shell=bash
# Shared by the install steps (sourced). Each step checks before it changes anything and says what it changed.
# Exit 2 = a manual step is needed (the message says which); agentctl install reports it and carries on.
set -euo pipefail
changed() { echo "changed: $*"; }
ok() { echo "ok: $*"; }
manual() { echo "MANUAL: $*"; exit 2; }
have() { command -v "$1" >/dev/null 2>&1; }
apt_install() {
  local missing=() p
  for p in "$@"; do dpkg -s "${p}" >/dev/null 2>&1 || missing+=("${p}"); done
  [ ${#missing[@]} -eq 0 ] && return 0
  DEBIAN_FRONTEND=noninteractive apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${missing[@]}" >/dev/null
  changed "installed ${missing[*]}"
}
