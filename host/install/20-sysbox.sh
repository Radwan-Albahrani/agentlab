#!/bin/bash
# Sysbox CE: agents get their own user namespace and run Docker inside without --privileged or unconfined profiles.
# sysbox-mgr hands each container a range of host uids; the agent's own rootless Docker maps 100000-165535 inside, so
# each container needs at least 165536 of them (the default is 65536).
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
[ "${AGENTLAB_ISOLATION}" = sysbox ] || { ok "isolation is ${AGENTLAB_ISOLATION}: Sysbox not needed"; exit 0; }
grep -qi microsoft /proc/version && manual "Sysbox cannot run on WSL: set isolation = \"unconfined\" (one person only)"
v=0.7.1
if ! dpkg -s sysbox-ce >/dev/null 2>&1; then
  [ -z "$(docker ps -q)" ] || echo "note: installing Sysbox restarts Docker; running containers restart with it"
  apt_install jq
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
fi
dropin=/etc/systemd/system/sysbox-mgr.service.d/agentlab.conf
if [ ! -f "${dropin}" ]; then
  cmd=$(systemctl show sysbox-mgr -p ExecStart --value | sed -n 's/.*argv\[\]=\([^;]*\);.*/\1/p' | xargs)
  case "${cmd}" in
    */sysbox-mgr) ;;
    *) manual "sysbox-mgr starts as '${cmd}': add --subid-range-size 262144 to it by hand (systemctl edit sysbox-mgr)" ;;
  esac
  mkdir -p "$(dirname "${dropin}")"
  printf '[Service]\nExecStart=\nExecStart=%s --subid-range-size 262144\n' "${cmd}" > "${dropin}"
  systemctl daemon-reload
  systemctl restart sysbox
  changed "sysbox-mgr gives each container 262144 uids (rootless Docker inside needs 165536)"
fi
if docker info --format '{{json .Runtimes}}' | grep -q sysbox-runc; then
  ok "sysbox-runc registered with Docker"
else
  echo "sysbox-runc is not registered with Docker"
  exit 1
fi
