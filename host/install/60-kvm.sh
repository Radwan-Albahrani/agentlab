#!/bin/bash
# Android emulator: needs /dev/kvm. Under Sysbox the agent's uid inside is not in the host's kvm group, so the device
# is made usable by everyone (what CI runners do); unconfined agents get the kvm group instead (group_add).
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
[ -n "${AGENTLAB_ANDROID}" ] || { ok "Android off"; exit 0; }
[ -e /dev/kvm ] || modprobe kvm_intel 2>/dev/null || modprobe kvm_amd 2>/dev/null || true
[ -e /dev/kvm ] || manual "no /dev/kvm: enable virtualization (VT-x / AMD-V) in the BIOS, or set [android] enabled = false"
rule=/etc/udev/rules.d/99-agentlab-kvm.rules
if [ "${AGENTLAB_ISOLATION}" = sysbox ] && [ ! -f "${rule}" ]; then
  echo 'KERNEL=="kvm", GROUP="kvm", MODE="0666", OPTIONS+="static_node=kvm"' > "${rule}"
  udevadm control --reload-rules && udevadm trigger --name-match=kvm
  changed "/dev/kvm usable by every agent"
fi
ok "/dev/kvm $(stat -c %A /dev/kvm)"
