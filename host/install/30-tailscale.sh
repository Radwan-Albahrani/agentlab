#!/bin/bash
# tailscale ingress: `tailscale serve` terminates HTTPS on the machine's MagicDNS name and adds Tailscale-User-Login,
# which the gate trusts (the firewall stops agents from forging it). 443 -> agents, hub_port -> the hub.
# Installs Tailscale with its official script and signs the machine in: with a saved auth key straight away,
# otherwise by printing the login link (exit 2; re-run once it's opened).
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
[ "${AGENTLAB_INGRESS}" = tailscale ] || { ok "ingress is ${AGENTLAB_INGRESS}: tailscale serve not needed"; exit 0; }
# Published-ports setups (the hub and every agent's T3 on host ports) keep their own network as the way in: leave
# Tailscale's settings alone.
[ -n "${AGENTLAB_SERVE}" ] || { ok "everything is on published ports: tailscale serve not used"; exit 0; }
# On WSL Tailscale usually runs on Windows: use its CLI (mirrored networking lets it reach WSL's loopback).
ts=tailscale
windows="/mnt/c/Program Files/Tailscale/tailscale.exe"
if ! have tailscale && grep -qi microsoft /proc/version && [ -x "${windows}" ]; then ts=${windows}; fi
if [ "${ts}" = tailscale ] && ! have tailscale; then
  curl -fsSL https://tailscale.com/install.sh | sh >/tmp/tailscale-install.log 2>&1 || {
    tail -20 /tmp/tailscale-install.log
    exit 1
  }
  changed "installed Tailscale"
fi
running() { "${ts}" status --json 2>/dev/null | jq -e '.BackendState == "Running"' >/dev/null; }
if ! running; then
  [ "${ts}" = tailscale ] || manual "sign in to Tailscale for Windows, then run agentctl install again"
  key="${AGENTLAB_DATA}/secrets/tailscale-authkey"
  if [ -s "${key}" ]; then
    tailscale up --auth-key="file:${key}" >/dev/null
    changed "signed this machine in to the tailnet with the saved auth key"
  else
    # `tailscale up` prints a login link and waits; the sign-in carries on in tailscaled after it's stopped
    url=$(timeout 20 tailscale up 2>&1 | grep -oE 'https://login\.tailscale\.com/[^[:space:]]+' | head -1 || true)
    manual "sign this machine in to your tailnet: open ${url:-the link from 'sudo tailscale up'} (or save an auth key: agentctl secret set tailscale-authkey), then run agentctl install again"
  fi
fi
"${ts}" status --json | jq -e '(.CertDomains // []) | length > 0' >/dev/null ||
  manual "turn on MagicDNS and HTTPS Certificates in the Tailscale admin console (DNS page: https://login.tailscale.com/admin/dns), then run agentctl install again"
status=$("${ts}" serve status --json 2>/dev/null || echo '{}')
if ! grep -q '127.0.0.1:8088' <<< "${status}"; then
  "${ts}" serve --bg --https=443 http://127.0.0.1:8088 >/dev/null
  changed "tailscale serve: 443 -> edge (agents)"
fi
if ! grep -q '127.0.0.1:8090' <<< "${status}"; then
  "${ts}" serve --bg "--https=${AGENTLAB_HUB_PORT}" http://127.0.0.1:8090 >/dev/null
  changed "tailscale serve: ${AGENTLAB_HUB_PORT} -> edge (hub)"
fi
ok "tailscale serve in place; the tailnet's access controls decide who reaches this machine"
