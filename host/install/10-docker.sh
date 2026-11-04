#!/bin/bash
# Docker, agentctl's tools, and br_netfilter so the agent firewall sees traffic between containers on one network.
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
if have docker && docker compose version >/dev/null 2>&1; then
  ok "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null)"
else
  apt_install ca-certificates curl gnupg
  # shellcheck disable=SC1091
  . /etc/os-release
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker >/dev/null
fi
apt_install nftables jq sqlite3 e2fsprogs git
if [ ! -f /etc/modules-load.d/agentlab.conf ]; then
  echo br_netfilter > /etc/modules-load.d/agentlab.conf
  changed "br_netfilter loads at boot"
fi
modprobe br_netfilter
if [ ! -f /etc/sysctl.d/90-agentlab.conf ] || [ "$(sysctl -n net.bridge.bridge-nf-call-iptables)" != 1 ]; then
  echo 'net.bridge.bridge-nf-call-iptables = 1' > /etc/sysctl.d/90-agentlab.conf
  sysctl -q -p /etc/sysctl.d/90-agentlab.conf
  changed "traffic between containers passes the firewall"
fi
