# gate

The gate decides who reaches what. It answers the edge's pass 1 (`GET /verify`, Traefik forwardAuth, on every
request) and serves its own pages in pass 2. It is the one place that says yes or no, so it fails closed: anything
it doesn't recognise is a 403. See `docs/architecture.md` ("Access modes", "Edge: two passes").

## Pass 1: `/verify`

1. **Who is this**, per `auth.mode`:
   - `cloudflare-access`: the `Cf-Access-Jwt-Assertion` header (or `CF_Authorization` cookie). RS256 only (`none` and
     HS* are refused, so nobody can forge one with the public key), signed by a key from
     `https://<team>.cloudflareaccess.com/cdn-cgi/access/certs`, `aud` = `auth.cloudflare.audience`, `iss` = that team
     URL, not expired (30 s leeway), with an `email` claim. On the main domain, Cloudflare's
     `Cf-Access-Authenticated-User-Email` must match the token when present.
   - `cloudflare-access` with `auth.cloudflare.https` (private over HTTPS), for requests that arrived over HTTPS
     (`X-Forwarded-Proto`): Access adds no token there, so the gate signs people in itself as an OIDC client of the
     `agentlab-<name> sign-in` application (`oidc.py`: authorization code with PKCE, state and nonce; the ID token
     checked against that application's keys, issuer, audience, expiry and nonce), then trusts its own session cookie
     (`__Host-agentlab_session`, encrypted and signed, per host, 12 hours). A page load without one is sent to sign
     in; anything else gets 401. `/_agentlab/oidc/callback` and `/_agentlab/oidc/logout` are answered here. Its
     secrets are files in `GATE_SECRETS`. Plain HTTP keeps the Access token until agentctl writes `https-live` there,
     then gets a 308 to HTTPS.
   - `tailscale`: `Tailscale-User-Login`, set by `tailscale serve`. Required (tagged devices have none).
   - `tinyauth`: `Remote-Email`, set by tinyauth's forwardAuth answer just before ours. Required.
   - `none`: everyone is `local@localhost`, an admin. Needs `GATE_ALLOW_NONE=1`.

   The `tailscale` / `tinyauth` headers are only trustworthy because pass 1 **deletes** client-sent `X-Agentlab-*` and
   `Remote-*` headers before anything else, `tailscale serve` overwrites its own, and agents can't open connections
   to the gate (nftables). The gate itself can't tell a forged header from a real one; the edge config is what keeps
   them out.
2. **Where to**: the edge stamps `X-Agentlab-Site: agent | hub | coolify` (after deleting any client copy), which is
   how Tailscale serves agents and hub on one name; any other value is a 403, and the host (lowercased, port stripped)
   must still be one of the cluster's names. Without the header the host decides (Tailscale's hub: the same name on
   `auth.hub_port`, via `X-Forwarded-Port` or the Host port). The pages in pass 2 need site `agent` the same way.
   - `hub_domain`: anyone who owns an agent, and admins.
   - `coolify_domain`: admins only.
   - `domain`: everyone verified. The agent: the `agentlab_view` cookie if it names an agent you may open (yours;
     admins: any), else your only agent, else `gate` (the picker).
   - anything else: 403. Hostnames are always compared case-insensitively (tinyauth's CVE-2026-77560 was a
     case-sensitive host match that failed open).
3. **Onboarding.** A T3 request (any path outside `/_agentlab`) for an agent you own whose onboarding isn't done gets
   `302` to `<hub>/agents/<id>/onboarding`. The gate asks `http://agent-<id>:8790/api/onboarding` (2 s timeout); `done`
   is cached forever, not-done for 10 s, and an agent that doesn't answer is let through (a sick Accounts app must not
   lock anyone out). Admins viewing someone else's agent are never redirected.

Allowed requests get `X-Agentlab-User`, `X-Agentlab-Admin` (`0`/`1`) and `X-Agentlab-Agent` (an agent id, `gate`, or
`none` on hub/Coolify without a chosen agent). The edge copies them onto the request (`authResponseHeaders`) and pass 2
routes on `X-Agentlab-Agent`. With HTTPS sign-in they also get `X-Agentlab-Proof`, an HMAC over the three (two
minutes), which the hub checks in place of the Access token.

## Pass 2: pages (main domain only)

Reached only through the edge, with pass 1's headers; a request without `X-Agentlab-User` gets 403.

| Path | What |
|---|---|
| `/_agentlab/` | picker and switcher: your agents (current one marked), its tools (chats, accounts, browser, terminal, files), onboarding status, the hub; admins also see everyone's agents, grouped by owner |
| `/_agentlab/view/<id>?next=/path` | switch to an agent you may open (cookie `agentlab_view`, Secure, HttpOnly, SameSite=Lax); otherwise 403 |
| `/_agentlab/view/me?next=/path` | clear the choice |
| anything else routed here | the same picker (people without an agent see "no agent yet") |

`next` must be a path on the same site (`/...`, never `//` or a backslash); anything else goes to `/`.

## Environment

| Variable | Default | |
|---|---|---|
| `GATE_CONFIG` | `/etc/agentlab/cluster.json` | re-read whenever it changes; a broken file keeps the last good one |
| `GATE_PORT` | `8080` | |
| `GATE_ALLOW_NONE` | unset | must be `1` for `auth.mode = "none"`. Without it the gate refuses to start, and denies everything if the config switches to `none` later |

`GET /health` answers `ok`.

## Tests

```
docker run --rm -v "$PWD:/repo:ro" -w /repo/gate python:3.12-alpine sh -c \
  'pip install -q -r requirements.txt && python -m unittest discover -s tests -t .'
```
