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
# The command-line tools need Java 17+. Distros carry different ones (Debian 13: 21 and 25; Ubuntu 24.04: 17 and 21),
# so take the first the host has, newest LTS first (same order as cli/agentlab/preflight.py).
jre=$(pick_package openjdk-21-jre-headless openjdk-25-jre-headless openjdk-17-jre-headless) ||
  { echo "unsupported host: apt has no Java 17+ (openjdk-21/25/17-jre-headless)"; exit 1; }
apt_install "${jre}" unzip
java=$(dpkg -L "${jre}" | grep -m1 '/bin/java$')
export JAVA_HOME=${java%/bin/java}  # this JRE even when an older default java is installed
tools=${sdk}/cmdline-tools/latest/bin/sdkmanager
if [ ! -x "${tools}" ]; then
  tmp=$(mktemp -d)
  curl -fsSL -o "${tmp}/tools.zip" https://dl.google.com/android/repository/commandlinetools-linux-13114758_latest.zip
  mkdir -p "${sdk}/cmdline-tools"
  unzip -q "${tmp}/tools.zip" -d "${tmp}"
  rm -rf "${sdk}/cmdline-tools/latest"
  mv "${tmp}/cmdline-tools" "${sdk}/cmdline-tools/latest"
fi
"${tools}" --sdk_root="${sdk}" --version >/dev/null 2>&1 ||
  { echo "sdkmanager does not run with ${jre}: $("${tools}" --sdk_root="${sdk}" --version 2>&1 | tail -1)"; exit 1; }
yes | "${tools}" --sdk_root="${sdk}" --licenses >/dev/null || true
"${tools}" --sdk_root="${sdk}" --install platform-tools emulator "${AGENTLAB_SYSTEM_IMAGE}" >/dev/null
chmod -R a+rX "${sdk}"
changed "Android SDK with ${AGENTLAB_SYSTEM_IMAGE} in ${sdk}"
