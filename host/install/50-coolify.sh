#!/bin/bash
# Coolify (deploy = "coolify"): installed by its own installer; agentctl then needs an API token. Coolify's UI only
# makes tokens for a signed-in user, so once the admin account exists the token is made directly as Coolify's own
# Sanctum record (the database keeps sha256(secret); the usable token is "<id>|<secret>").
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
[ "${AGENTLAB_DEPLOY}" = coolify ] || { ok "deploy is ${AGENTLAB_DEPLOY}: Coolify not needed"; exit 0; }
if ! docker inspect coolify >/dev/null 2>&1; then
  echo "installing Coolify with its official installer (cdn.coollabs.io/coolify/install.sh)"
  if ! curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash > /tmp/coolify-install.log 2>&1; then
    tail -20 /tmp/coolify-install.log
    exit 1
  fi
  changed "installed Coolify"
fi
if [ -s "${AGENTLAB_COOLIFY_TOKEN}" ]; then
  code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $(cat "${AGENTLAB_COOLIFY_TOKEN}")" \
    "${AGENTLAB_COOLIFY_URL}/api/v1/version")
  [ "${code}" = 200 ] && { ok "Coolify token works"; exit 0; }
  echo "the token in ${AGENTLAB_COOLIFY_TOKEN} is refused (HTTP ${code}); making a new one"
fi
# shellcheck disable=SC2016  # PHP, not shell
users=$(docker exec coolify php artisan tinker --execute='echo \App\Models\User::count();' 2>/dev/null | tr -dc 0-9)
[ "${users:-0}" -gt 0 ] ||
  manual "create Coolify's admin account: ssh -L 8000:127.0.0.1:8000 <server>, open http://localhost:8000 and register; then sudo agentctl install"
# shellcheck disable=SC2016  # PHP, not shell
docker exec coolify php artisan tinker --execute='$plain = Illuminate\Support\Str::random(48);
  $t = \Laravel\Sanctum\PersonalAccessToken::forceCreate(["tokenable_type" => App\Models\User::class, "tokenable_id" => 0,
    "name" => "agentlab", "token" => hash("sha256", $plain), "abilities" => ["root"], "team_id" => 0]);
  file_put_contents("/tmp/agentlab-coolify-token", $t->id . "|" . $plain);' >/dev/null
install -m 600 /dev/null "${AGENTLAB_COOLIFY_TOKEN}"
docker exec coolify sh -c 'cat /tmp/agentlab-coolify-token; rm -f /tmp/agentlab-coolify-token' > "${AGENTLAB_COOLIFY_TOKEN}"
changed "created a Coolify API token for agentctl (${AGENTLAB_COOLIFY_TOKEN})"
