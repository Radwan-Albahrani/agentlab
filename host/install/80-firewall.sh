#!/bin/bash
# The agent firewall (rules rendered by agentctl apply). ufw can't stand in: Docker's forwarding bypasses its chains.
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
rules=${AGENTLAB_DATA}/rendered/firewall/agentlab.nft
systemctl enable -q agentlab-firewall.service
if [ -f "${rules}" ]; then
  nft -c -f "${rules}" || { echo "the rendered rules don't load"; exit 1; }
  systemctl restart agentlab-firewall.service
  ok "firewall loaded"
else
  ok "firewall unit enabled; agentctl apply writes the rules and loads them"
fi
