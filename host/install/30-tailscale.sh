#!/bin/bash
# tailscale ingress: `tailscale serve` terminates HTTPS on the machine's MagicDNS name and adds Tailscale-User-Login,
# which the gate trusts (the firewall stops agents from forging it). 443 -> agents, hub_port -> the hub.
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
[ "${AGENTLAB_INGRESS}" = tailscale ] || { ok "ingress is ${AGENTLAB_INGRESS}: tailscale serve not needed"; exit 0; }
have tailscale || manual "install Tailscale (https://tailscale.com/download/linux), then: sudo tailscale up"
tailscale status --json | jq -e '.BackendState == "Running"' >/dev/null || manual "run: sudo tailscale up"
status=$(tailscale serve status --json 2>/dev/null || echo '{}')
if ! grep -q '127.0.0.1:8088' <<< "${status}"; then
  tailscale serve --bg --https=443 http://127.0.0.1:8088 >/dev/null
  changed "tailscale serve: 443 -> edge (agents)"
fi
if ! grep -q '127.0.0.1:8090' <<< "${status}"; then
  tailscale serve --bg "--https=${AGENTLAB_HUB_PORT}" http://127.0.0.1:8090 >/dev/null
  changed "tailscale serve: ${AGENTLAB_HUB_PORT} -> edge (hub)"
fi
ok "tailscale serve in place; the tailnet ACL (admin console) decides who reaches this machine"
