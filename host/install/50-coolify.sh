#!/bin/bash
# Coolify (deploy = "coolify"): installed by its official installer, which also creates the first (root) account from
# ROOT_USERNAME / ROOT_USER_EMAIL / ROOT_USER_PASSWORD (documented: coolify.io/docs/knowledge-base/server/
# create-root-user-with-environment-variables); the login is kept root-only in the secrets folder. Coolify makes API
# tokens only in its UI, so that one step is the admin's: the message says where, and `agentctl secret set coolify`
# saves it.
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
[ "${AGENTLAB_DEPLOY}" = coolify ] || { ok "deploy is ${AGENTLAB_DEPLOY}: Coolify not needed"; exit 0; }
login="${AGENTLAB_DATA}/secrets/coolify-login.txt"
if ! docker inspect coolify >/dev/null 2>&1; then
  # Coolify wants upper and lower case, a digit and a symbol
  password="$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24)Aa1!"
  install -d -m 700 "${AGENTLAB_DATA}/secrets"
  install -m 600 /dev/null "${login}"
  printf 'email: %s\npassword: %s\n' "${AGENTLAB_ADMIN_EMAIL}" "${password}" > "${login}"
  echo "installing Coolify with its official installer (cdn.coollabs.io/coolify/install.sh)"
  if ! curl -fsSL https://cdn.coollabs.io/coolify/install.sh |
    env ROOT_USERNAME=admin ROOT_USER_EMAIL="${AGENTLAB_ADMIN_EMAIL}" ROOT_USER_PASSWORD="${password}" bash \
      > /tmp/coolify-install.log 2>&1; then
    tail -20 /tmp/coolify-install.log
    exit 1
  fi
  changed "installed Coolify; its admin login is in ${login}"
fi
if [ -s "${AGENTLAB_COOLIFY_TOKEN}" ]; then
  code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $(cat "${AGENTLAB_COOLIFY_TOKEN}")" \
    "${AGENTLAB_COOLIFY_URL}/api/v1/version")
  [ "${code}" = 200 ] && { ok "Coolify token works"; exit 0; }
  echo "the saved Coolify token is refused (HTTP ${code})"
fi
where="${AGENTLAB_COOLIFY_URL}"
[ -n "${AGENTLAB_COOLIFY_DOMAIN}" ] && where="https://${AGENTLAB_COOLIFY_DOMAIN}"
[ -s "${login}" ] && signin=" (your login is in ${login})" || signin=""
manual "Coolify needs one API token from you: sign in at ${where}${signin}, open Keys & Tokens → API tokens, create one with root permission, and save it with: agentctl secret set coolify"
