#!/bin/bash
# The host services as systemd units, rendered from host/systemd with this cluster's paths and limits.
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
src=${AGENTLAB_REPO}/host/systemd
units=(agentlab.slice agentlab-disks.service agentlab-throttle.service agentlab-watch.service
  agentlab-janitor.service agentlab-janitor.timer agentlab-backup.service agentlab-backup.timer
  agentlab-firewall.service agentlab-update.service agentlab-update.timer)
# private names run cloudflared as a container in the core stack instead
[ "${AGENTLAB_INGRESS}" = cloudflared ] && [ "${AGENTLAB_CF_NETWORK:-}" != private ] && units+=(cloudflared.service)
any=""
for u in "${units[@]}"; do
  new=$(sed -e "s|@REPO@|${AGENTLAB_REPO}|g" -e "s|@DATA@|${AGENTLAB_DATA}|g" -e "s|@CONFIG@|${AGENTLAB_CONFIG}|g" \
    -e "s|@CLUSTER@|${AGENTLAB_DATA}/rendered/cluster.json|g" -e "s|@MEMORY_HIGH@|${AGENTLAB_MEMORY_HIGH}|g" \
    -e "s|@MEMORY_MAX@|${AGENTLAB_MEMORY_MAX}|g" -e "s|@BACKUP_TIME@|${AGENTLAB_BACKUP_TIME}|g" \
    -e "s|@UPDATE_TIME@|${AGENTLAB_UPDATE_TIME}|g" "${src}/${u}")
  if [ "${new}" != "$(cat "/etc/systemd/system/${u}" 2>/dev/null)" ]; then
    printf '%s\n' "${new}" > "/etc/systemd/system/${u}"
    changed "${u}"
    any=1
  fi
done
[ -n "${any}" ] && systemctl daemon-reload
systemctl start agentlab.slice
enable=(agentlab-disks.service agentlab-throttle.service agentlab-watch.service agentlab-janitor.timer)
# Nightly backups are optional ([backups] enabled); `agentctl backup run` works either way.
if [ -n "${AGENTLAB_BACKUPS}" ]; then
  enable+=(agentlab-backup.timer)
elif systemctl is-enabled -q agentlab-backup.timer 2>/dev/null; then
  systemctl disable -q --now agentlab-backup.timer
  changed "agentlab-backup.timer off ([backups] enabled = false)"
fi
# Nightly self-update is opt-in ([updates] agentlab = "daily"); `agentctl update` works either way.
if [ -n "${AGENTLAB_UPDATES}" ]; then
  enable+=(agentlab-update.timer)
elif systemctl is-enabled -q agentlab-update.timer 2>/dev/null; then
  systemctl disable -q --now agentlab-update.timer
  changed "agentlab-update.timer off ([updates] agentlab = \"off\")"
fi
for u in "${enable[@]}"; do
  systemctl enable -q "${u}"
  if [ -n "${any}" ] || ! systemctl is-active -q "${u}"; then systemctl restart "${u}"; fi
done
ok "agentlab units enabled"
