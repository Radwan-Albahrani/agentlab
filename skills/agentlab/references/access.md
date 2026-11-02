# Access modes: setup per mode

Every mode ends the same way: people open `https://<domain>`, prove who they are, and land on their own agent (or a
picker if they have several). Only the agent owners and `auth.admins` get in, plus, with `[auth] allow_domains =
["example.com"]` (Cloudflare Access and tinyauth), anyone with an email in those domains: they can sign in, but only
owners get an agent (the rest see "no agent yet" until an admin adds one), and admins still come only from
`auth.admins`. Pick one mode per cluster.

Steps marked **human** need someone with the account; give them the exact text below and wait.

## cloudflare-access

People sign in at Cloudflare's edge (one-time PIN by email, Google, or any login method set up in Zero Trust); a Cloudflare Tunnel brings
traffic to the server, so the server opens no ports. Separate from any tunnel the company already uses for other
things: this cluster gets its own tunnel and its own Access applications, and being allowed here grants nothing
anywhere else.

Config:

```toml
[cluster]
domain = "agents.example.com"          # first-level under the zone: covered by the free certificate
hub_domain = "agents-hub.example.com"
pair_domain = "{id}-t3.example.com"    # optional: lets the T3 desktop/mobile app connect (see below)

[auth]
mode = "cloudflare-access"
admins = ["admin@example.com"]

[auth.cloudflare]
team = "example"                       # the part before .cloudflareaccess.com

[cloudflare]
account_id = "..."
zone = "example.com"
api_token_file = "/srv/agentlab/secrets/cloudflare-api.token"
```

1. Sign-in method: **any Zero Trust login method works**. The one-time PIN by email needs no setup at all (people
   type their email, get a code). Google Workspace or Microsoft Entra ID are optional, for one-click sign-in:
   - **human**, Google Workspace: Google Cloud console → OAuth consent screen (User type **Internal**) → Credentials →
     OAuth client ID (Web application), redirect URI `https://<team>.cloudflareaccess.com/cdn-cgi/access/callback`;
     then Zero Trust → Settings → Authentication → Login methods → Add new → **Google Workspace**, paste client
     id/secret, Workspace domain = the company domain, **Test**. Microsoft 365 companies use **Microsoft Entra ID**.
   - Other apps in the account keep their own methods (each Access application picks its own).
   - Leave `[auth.cloudflare] login_method` empty to offer every method the account has, or set it to one method's
     exact name (`"One-time PIN"`, `"Google Workspace"`) so the agents' application offers only that one.
2. **human**: Cloudflare dashboard → My Profile → API Tokens → Create token → Custom token, with these permissions
   (names as the token page shows them):
   - Account · **Cloudflare One Connector: cloudflared** → Edit (older accounts: **Argo Tunnel (Legacy)** → Edit;
     the docs call it Cloudflare Tunnel Write)
   - Account · **Access: Apps and Policies** → Edit
   - Account · **Access: Identity Providers** → Read (only for `login_method`; older dashboards bundle it as "Access: Organizations, Identity Providers, and Groups"). Not Groups, not Organizations.
   - Zone · **DNS** → Edit (not "Zone DNS Settings"), with Zone Resources limited to the cluster's zone

   Put it in `api_token_file` (`sudo install -m 600 /dev/stdin <file>`, paste, Ctrl-D), then
   `sudo agentctl doctor --json`: it verifies the token and probes each area read-only, and a missing one shows as
   "token lacks <permission>" with that permission's name as the fix.
3. `sudo agentctl cloudflare setup --dry-run --json`, show the plan, then without `--dry-run`. It creates the tunnel,
   DNS records for exactly the cluster's hostnames (no wildcard), the Access application (allow list = owners +
   admins), the Bypass application for pair hosts, and writes the AUD tag into the config.
4. `sudo agentctl apply --json`, then `doctor --json`: `cloudflared` connected, Access app found, AUD matches.

Each `apply` re-syncs the Access allow list with the config (the people by name, plus an email-domain rule per
`allow_domains` entry), so adding a person needs no dashboard visit.

**Desktop / mobile app**: apps can't do the browser sign-in, so with `pair_domain` set each agent gets its own
hostname that skips Access and goes straight to that agent's T3, which only accepts devices paired from that person's
hub (one-time links). Without `pair_domain`, people use T3 in the browser only.

**Certificates**: Cloudflare's free certificate covers `*.example.com` only. Keep every hostname one level under the
zone (`agents.example.com`, `sara-t3.example.com`); `agents.sub.example.com` would need Advanced Certificate Manager.

## tailscale

People are on the company tailnet; `tailscale serve` on the server gives HTTPS and tells the edge who each request is
from. Nothing is public. Simplest for small teams already on Tailscale.

Config:

```toml
[cluster]
domain = "agents.tailnet-name.ts.net"   # the server's MagicDNS name
hub_domain = "agents.tailnet-name.ts.net"

[auth]
mode = "tailscale"
admins = ["admin@example.com"]          # tailnet login names
hub_port = 8443                         # hub is served on this port of the same name
```

1. **human**: Tailscale admin console → DNS: MagicDNS on and HTTPS Certificates enabled.
2. `agentctl install` installs Tailscale; **human** runs `sudo tailscale up --hostname agents` on the server and
   approves it (or provides an auth key file).
3. **human**: access controls must let the owners reach the server on 443 and `hub_port`, and nothing more is needed;
   don't share the machine with people who shouldn't get in (Tailscale identity is the sign-in here).
   `doctor` prints a suggested ACL snippet.
4. `sudo agentctl apply --json`; it configures `tailscale serve` for 443 and `hub_port`.

**Desktop / mobile app**: works directly: the app connects to the tailnet URL from a device on the tailnet, and the
person's tailnet identity picks their agent. No `pair_domain`.

Logins are tailnet login names (often emails, sometimes `name@github`): use exactly what `tailscale status` shows as
owners and admins.

## tinyauth

Google sign-in handled on the server by tinyauth. Use when the company has no Cloudflare Access and no tailnet.
The server is reachable from the internet (public ingress) or through a Cloudflare Tunnel without Access.

Config:

```toml
[cluster]
domain = "agents.example.com"
hub_domain = "agents-hub.example.com"
pair_domain = "{id}-t3.example.com"     # optional, as in cloudflare-access

[auth]
mode = "tinyauth"
ingress = "public"                      # or "cloudflared"
admins = ["admin@example.com"]

[auth.tinyauth]
domain = "agents-auth.example.com"      # tinyauth's login page; same parent domain as the others (cookies)
google_client_id_file = "/srv/agentlab/secrets/tinyauth-google-id"
google_client_secret_file = "/srv/agentlab/secrets/tinyauth-google-secret"
```

1. **human**: Google Cloud console → OAuth client (Web), redirect URI `https://<auth.tinyauth.domain>/api/oauth/callback/google`.
   Put the id and secret in the two files.
2. Ingress:
   - `public`: **human** points DNS A/AAAA records for every cluster hostname (domain, hub, auth, each pair host) at
     the server (no proxy), and opens TCP 80 and 443 to it. The edge gets Let's Encrypt certificates itself.
   - `cloudflared`: as in cloudflare-access steps 2–3 but `agentctl cloudflare setup` skips the Access applications.
3. `sudo agentctl apply --json`; tinyauth's allow list is rendered from owners + admins (plus a regex per `allow_domains` entry) on every
   apply.

`doctor` refuses tinyauth versions affected by CVE-2026-77560 (per-app allowlist bypass with mixed-case hosts); the
gate also checks identity itself, so a tinyauth bug alone can't open someone else's agent.

## none (testing only)

`auth.mode = "none"` lets everyone in as admin and binds only to loopback. Use it to try agentlab on a laptop
(`curl -H 'Host: agents.localhost' http://127.0.0.1:8088/`). Never on a server other people can reach.
