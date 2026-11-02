#!/bin/bash
# cloudflared ingress: the tunnel is the one way in. Its token comes from `agentctl cloudflare setup`.
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
[ "${AGENTLAB_INGRESS}" = cloudflared ] || { ok "ingress is ${AGENTLAB_INGRESS}: cloudflared not needed"; exit 0; }
if ! have cloudflared; then
  install -m 0755 -d /usr/share/keyrings
  curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg -o /usr/share/keyrings/cloudflare-main.gpg
  echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' \
    > /etc/apt/sources.list.d/cloudflared.list
  apt_install cloudflared
fi
# agentctl install creates the tunnel before this step whenever the Cloudflare API token is saved
[ -s "${AGENTLAB_TUNNEL_TOKEN}" ] ||
  manual "save your Cloudflare API token (agentctl secret set cloudflare-api), then run agentctl setup again"
systemctl enable -q cloudflared 2>/dev/null || true
if ! systemctl is-active -q cloudflared; then
  systemctl restart cloudflared
  changed "cloudflared started"
fi
ok "cloudflared $(systemctl is-active cloudflared)"
