#!/bin/bash
# cloudflared ingress: a host unit for public names, a core-stack container for private names.
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# Stops only our host unit (it reads agentlab's token file), never someone else's cloudflared.
retire_host_tunnel() {
  local unit=$1
  grep -qs 'secrets/cloudflare-tunnel.token' "${unit}" || return 0
  if systemctl is-enabled -q cloudflared 2>/dev/null || systemctl is-active -q cloudflared 2>/dev/null; then
    systemctl disable -q --now cloudflared
    changed "host cloudflared stopped (the tunnel runs in the core stack for private names)"
  fi
}

main() {
  [ "${AGENTLAB_INGRESS}" = cloudflared ] || { ok "ingress is ${AGENTLAB_INGRESS}: cloudflared not needed"; exit 0; }
  [ -s "${AGENTLAB_TUNNEL_TOKEN}" ] ||
    manual "save your Cloudflare API token (agentctl secret set cloudflare-api), then run agentctl setup again"
  if [ "${AGENTLAB_CF_NETWORK:-}" = private ]; then
    retire_host_tunnel /etc/systemd/system/cloudflared.service
    ok "cloudflared runs as a container in the core stack (private names)"
    exit 0
  fi
  if ! have cloudflared; then
    install -m 0755 -d /usr/share/keyrings
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg -o /usr/share/keyrings/cloudflare-main.gpg
    echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' \
      > /etc/apt/sources.list.d/cloudflared.list
    apt_install cloudflared
  fi
  systemctl enable -q cloudflared 2>/dev/null || true
  if ! systemctl is-active -q cloudflared; then
    systemctl restart cloudflared
    changed "cloudflared started"
  fi
  ok "cloudflared $(systemctl is-active cloudflared)"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then main "$@"; fi
