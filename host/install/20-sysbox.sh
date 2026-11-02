#!/bin/bash
# Sysbox CE: agents get their own user namespace and run Docker inside without --privileged or unconfined profiles.
# Each container gets Sysbox's fixed 65536-id range; the agent's dockerd runs as container root inside it (see the
# image's agent-dockerd), so sysbox-mgr needs no options of its own.
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
v=0.7.1
OLD_DROPIN=/etc/systemd/system/sysbox-mgr.service.d/agentlab.conf

install_sysbox() {
  dpkg -s sysbox-ce >/dev/null 2>&1 && return 0
  [ -z "$(docker ps -q)" ] || echo "note: installing Sysbox restarts Docker; running containers restart with it"
  apt_install jq
  local deb tmp want got
  deb=sysbox-ce_${v}.linux_$(dpkg --print-architecture).deb
  tmp=$(mktemp -d)
  curl -fsSL -o "${tmp}/${deb}" "https://github.com/nestybox/sysbox/releases/download/v${v}/${deb}"
  want=$(curl -fsSL "https://api.github.com/repos/nestybox/sysbox/releases/tags/v${v}" |
    jq -r --arg n "${deb}" '.assets[] | select(.name==$n) | .digest' | sed 's/^sha256://')
  got=$(sha256sum "${tmp}/${deb}" | cut -d' ' -f1)
  if [ -z "${want}" ] || [ "${want}" = null ] || [ "${want}" != "${got}" ]; then
    echo "Sysbox ${deb}: published checksum missing or different; not installing"
    exit 1
  fi
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${tmp}/${deb}" >/dev/null
  changed "installed Sysbox CE ${v}"
}

# Earlier agentlab versions added a sysbox-mgr drop-in with --subid-range-size, a flag Sysbox doesn't have: sysbox-mgr
# then refuses to start. Remove exactly that file of ours, and only if it is ours.
remove_old_dropin() {
  local dropin=$1
  [ -f "${dropin}" ] || return 0
  grep -q -- '--subid-range-size' "${dropin}" || return 0
  rm -f "${dropin}"
  rmdir --ignore-fail-on-non-empty "$(dirname "${dropin}")"
  systemctl daemon-reload
  systemctl restart sysbox
  changed "removed ${dropin} (an unsupported sysbox-mgr flag from an earlier agentlab)"
}

main() {
  [ "${AGENTLAB_ISOLATION}" = sysbox ] || { ok "isolation is ${AGENTLAB_ISOLATION}: Sysbox not needed"; exit 0; }
  grep -qi microsoft /proc/version && manual "Sysbox cannot run on WSL: set isolation = \"unconfined\" (one person only)"
  install_sysbox
  remove_old_dropin "${OLD_DROPIN}"
  if ! systemctl is-active --quiet sysbox; then
    systemctl restart sysbox || true
    systemctl is-active --quiet sysbox || { echo "sysbox is not running: journalctl -u sysbox-mgr -u sysbox-fs"; exit 1; }
    changed "started Sysbox"
  fi
  if grep -q sysbox-runc <<<"$(docker info --format '{{json .Runtimes}}')"; then
    ok "sysbox-runc registered with Docker"
  else
    echo "sysbox-runc is not registered with Docker"
    exit 1
  fi
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then main "$@"; fi
