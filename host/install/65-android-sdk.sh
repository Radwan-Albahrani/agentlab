#!/bin/bash
# One Android SDK for every agent (mounted read-only): platform-tools, the emulator and the configured system image.
# Installing it accepts the Android SDK licenses (https://developer.android.com/studio/terms).
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
[ -n "${AGENTLAB_ANDROID}" ] || { ok "Android off"; exit 0; }
sdk=${AGENTLAB_DATA}/shared/android-sdk
image_dir=${sdk}/$(tr ';' '/' <<< "${AGENTLAB_SYSTEM_IMAGE}")
if [ -x "${sdk}/emulator/emulator" ] && [ -d "${image_dir}" ]; then
  ok "Android SDK in ${sdk}"
  exit 0
fi
apt_install openjdk-17-jre-headless unzip
tools=${sdk}/cmdline-tools/latest/bin/sdkmanager
if [ ! -x "${tools}" ]; then
  tmp=$(mktemp -d)
  curl -fsSL -o "${tmp}/tools.zip" https://dl.google.com/android/repository/commandlinetools-linux-13114758_latest.zip
  mkdir -p "${sdk}/cmdline-tools"
  unzip -q "${tmp}/tools.zip" -d "${tmp}"
  rm -rf "${sdk}/cmdline-tools/latest"
  mv "${tmp}/cmdline-tools" "${sdk}/cmdline-tools/latest"
fi
yes | "${tools}" --sdk_root="${sdk}" --licenses >/dev/null || true
"${tools}" --sdk_root="${sdk}" --install platform-tools emulator "${AGENTLAB_SYSTEM_IMAGE}" >/dev/null
chmod -R a+rX "${sdk}"
changed "Android SDK with ${AGENTLAB_SYSTEM_IMAGE} in ${sdk}"
