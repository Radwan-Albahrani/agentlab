#!/bin/bash
# cloudflared ingress: the tunnel is the one way in. Its token comes from `agentctl cloudflare setup`.
# Public names: cloudflared runs on this host and dials the edge on loopback. Private names (network = "private"):
# it runs as a container in the core stack next to the edge instead, so it needs no host port (Coolify's proxy may
# hold 80) and nothing on the host has to resolve the names.
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# Our host unit from an earlier public setup would run the same tunnel a second time; only ours (it reads agentlab's
# token file) is stopped, never a cloudflared someone else runs.
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
  # agentctl install creates the tunnel before this step whenever the Cloudflare API token is saved
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
