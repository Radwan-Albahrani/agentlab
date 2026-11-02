# Architecture

agentlab turns one Linux server into a private cluster of AI coding agents: every person gets their own agent
workspace (T3 chats, Claude Code / Codex with their own accounts, a browser, Docker, a terminal, files, an Android
emulator), signs in through the cluster's access mode, and can reach only their own workspace. The admin can reach everything. One config file describes the
cluster; `agentctl` makes the server match it.

This page is the contract every part of the repo follows. Change it first, then the code.

## The pieces

```
           person's browser
                 │  https://agents.example.com
                 ▼
   sign-in: Cloudflare Access │ tailscale serve │ tinyauth
                 │
                 ▼  cloudflared / tailscale serve (host) ──► 127.0.0.1:8088
   ┌──────────────────────── server ─────────────────────────────────────┐
   │  edge (Traefik) pass 1 ─► gate /verify (who you are, which agent)   │
   │  edge pass 2 (127.0.0.1:8089) routes on the gate's answer           │
   │        │                                                             │
   │        ├─► agent-adam:3773 (T3)     ┐ network agentlab-adam          │
   │        ├─► agent-sara:3773          ┐ network agentlab-sara          │
   │        └─► hub:8080 (admin)         ┐ network agentlab-edge          │
   │  host services: throttle broker, watcher, janitor, backups,          │
   │                 storage (shared or per person), agentlab.slice cap  │
   └──────────────────────────────────────────────────────────────────────┘
```

| Part | Folder | What it is |
|---|---|---|
| `agentctl` | `cli/` | Python 3.12 stdlib CLI. Reads `cluster.toml`, installs host prerequisites, renders everything into `<data>/rendered/`, deploys (Coolify or plain Compose), manages agents, Cloudflare and backups. |
| agent image | `image/` | One image for every agent: T3, Claude Code, Codex, gh, Chrome + noVNC, ttyd terminal, its own Docker on demand, Android emulator on demand, the Accounts page, throttle shims. |
| gate | `gate/` | Traefik forwardAuth service: who the person is (per access mode), which agent they get, onboarding redirects. Also serves the `/_agentlab/` menu and picker. |
| hub | `hub/` | Dashboard (Python backend + React web), scoped per person; admins also get the cluster screens. |
| companion | `companion/` | Slack companion template + base image; each companion runs its agent's own checkout. |
| host | `host/` | Host-side services: throttle broker, watcher (hub requests), pool janitor, backups, systemd units, install steps. |
| skill | `skills/agentlab/` | Instructions for an AI agent that installs and operates a cluster over SSH. |

## Access modes

How people reach the cluster and prove who they are is pluggable (`[auth]` in `cluster.toml`). Everything behind
the edge is the same in every mode.

| `auth.mode` | Sign-in | Ingress (`auth.ingress`, default) | Identity the gate trusts |
|---|---|---|---|
| `cloudflare-access` | Cloudflare Access (any Zero Trust login method; one-time PIN by email needs no setup) | `cloudflared` tunnel → `127.0.0.1:8088` | `Cf-Access-Jwt-Assertion`, verified (RS256, `aud`, `iss`, expiry) |
| `tailscale` | being on the tailnet | `tailscale serve` → `127.0.0.1:8088` | `Tailscale-User-Login`, set by `tailscale serve` |
| `tinyauth` | tinyauth (Google OAuth etc.), runs in the core stack | `public` (edge on :80/:443, Let's Encrypt) or `cloudflared` (tunnel, no Access) | `Remote-Email`, set by tinyauth's forwardAuth response |
| `none` | nobody: local testing only (gate needs `GATE_ALLOW_NONE=1`) | loopback | everyone is admin |

Allowed people are always the agent owners plus `auth.admins`, plus (cloudflare-access, tinyauth) everyone in `auth.allow_domains` (they sign in but get an agent only if they own one); `agentctl apply` pushes that list to the sign-in
system where it can (Cloudflare Access policy, tinyauth whitelist; for Tailscale the tailnet ACL is the admin's job
and `doctor` explains it).

**Cloudflare networks.** `[auth.cloudflare] network = "private"` (the default) publishes nothing: the tunnel carries
the cluster's names as private hostname routes (`/zerotrust/routes/hostname`, comment `agentlab-<name>`), so only
devices on the organization's Cloudflare One (WARP) client reach them, through Gateway. cloudflared resolves each name
on the host, where `apply` keeps a marked block in `/etc/hosts` pointing them at `127.0.0.1`, and connects on port 80,
which the edge also publishes on loopback. The Access application has private destinations (`port_range` 80) and
`allow_authenticate_via_warp`, so the client session signs people in (the T3 apps included) and Access hands the
origin the same `Cf-Access-Jwt-Assertion` it does for public apps: plain HTTP inside the client's tunnel is what lets
it do that without Gateway TLS decryption. agentlab's own public DNS records and the pair-host Bypass app are removed;
`pair_domain` is refused. `network = "public"` is the public-hostname setup, and `require_warp = true` adds a
`device_posture` require rule (the account's Gateway posture check) to the people policy there.

**Published ports (one person).** With `auth.mode` `tailscale` or `none` and a single owner, `[agents.publish]` and
`[hub] publish` put the tools on host ports, reached over the person's own network (tailnet or LAN).
When the hub and every agent's T3 are published, agentlab doesn't use `tailscale serve` or tailnet HTTPS at all and
never touches Tailscale's settings; links (pairing, Open T3, Files, the browser view) are built as
`http://<the host the page was opened on>:<port>`.

## Edge: two passes

The edge (Traefik) routes in two passes so identity-based routing works in every mode and can't be spoofed:

1. **Pass 1, entrypoint `ingress`** (container `:8088`, published `127.0.0.1:8088`; `public` ingress also binds
   `:80/:443`). Per host (`domain`, `hub_domain`, `coolify_domain`): a `headers` middleware deletes every client-sent
   `X-Agentlab-*` header (and `Remote-*` in tinyauth mode) and stamps `X-Agentlab-Site: agent|hub|coolify` → tinyauth forwardAuth (tinyauth mode only) → **gate
   forwardAuth** `/verify` with `authResponseHeaders: [X-Agentlab-User, X-Agentlab-Admin, X-Agentlab-Agent]` →
   service `http://127.0.0.1:8089` (the edge itself, pass 2), Host header kept.
2. **Pass 2, entrypoint `routed`** bound to `127.0.0.1:8089` inside the edge container, so only pass 1 can reach it.
   Routers match `Header(X-Agentlab-Site, agent) && Header(X-Agentlab-Agent, <id>)` plus the paths below (the site
   header, not `Host()`, is what lets tailscale mode serve agents and the hub on one name); `X-Agentlab-Agent: gate`
   → the gate (menu, picker, "no agent yet"); site `hub` → hub; site `coolify` → host `:8000`. A lowest-priority catch-all
   returns 404.

The gate decides everything in pass 1: who you are (per mode), which agent you get (an admin's `agentlab_view` cookie
naming an agent this person may open, else their only agent, else `gate` (the picker)), whether you may (hub: anyone
with an agent; coolify: admins only), and onboarding (below). Routers in pass 2 only follow its answer.

**Several agents per person.** A person may own any number of agents (`owner` repeats). The agents you may open are
the ones you own (admins: all). The `agentlab_view=<id>` cookie picks one of them; with no valid cookie and exactly one
agent you get that one, with several you get the gate's picker (`/_agentlab/`, which also switches any time). A cookie
naming an agent you may not open is ignored.

## Security model

1. **Nothing listens publicly** except with `public` ingress. The edge's ingress is on host loopback; only
   `cloudflared` or `tailscale serve` on the host reach it. Agent containers publish no host ports.
2. **Identity is checked on the server**, never taken from the client: in pass 1 the gate verifies the Access JWT
   (cloudflare) or reads a header that `tailscale serve` / tinyauth set and that pass 1 deleted from the client
   request first. Pass 2 is unreachable from outside the edge container.
3. **Agents can't see each other or open connections to shared services.** Each agent sits alone on its own Docker
   network `agentlab-<id>` with a fixed subnet; the edge, gate, hub and its companions join it. `agentctl install`
   writes nftables rules (table `agentlab`): an agent container may not open NEW connections to anything on its
   network (the edge, gate, hub and companions connect to it, never the reverse) or to the host (Docker's DNS answers inside the container, so names still resolve). Replies
   are allowed. This is what makes trusting `tailscale serve` / tinyauth headers safe. The rules know an agent by its
   address on `agentlab-<id>`, so an agent container is kept on that network only: Coolify connects every container
   it deploys to a network of its own, and `apply` (then the watcher, whenever Coolify recreates one) takes agents
   off it again.
4. **Containers are isolated by Sysbox** (`isolation = "sysbox"`): each agent is a user-namespaced container with
   default seccomp/AppArmor, and runs its own dockerd as container root (an unprivileged host user under Sysbox),
   started through a single sudo rule; everything else runs as the agent user. `isolation = "unconfined"` is the WSL fallback (Sysbox
   can't run on WSL) and is meant for single-person setups only; `agentctl doctor` warns about it when more than one
   person has an agent.
5. **Storage is a choice** (`[storage] mode`): `shared` (default) puts every agent under one pool, either a plain
   directory or, with `pool_size` set, a fixed-size ext4 loop image so agents can't fill the host; `per-person` gives
   each owner their own fixed-size image (`[storage] person_size`, overridable per agent owner) shared by all their
   agents, so one person filling a disk can't stop anyone else. The janitor keeps either tidy.
6. **T3 has its own sign-in too.** T3 only answers paired devices (bearer sessions from one-time pairing links), so
   even a routing mistake doesn't open someone's chats.
7. **The admin sees everything.** Admins (listed in `auth.admins`) can open every agent and the hub. People should be
   told this.

## Hostnames and routing

First-level hostnames, so Cloudflare's free Universal SSL covers them and no wildcard DNS is needed:

| Host | What | Who |
|---|---|---|
| `cluster.domain` (e.g. `agents.example.com`) | **your own agent**, chosen by who you signed in as | anyone with an agent; admins |
| `cluster.hub_domain` (e.g. `agents-hub.example.com`) | the hub, scoped to you (see "Your hub") | anyone with an agent; admins |
| `cluster.coolify_domain` (optional) | Coolify UI (`host:8000`) | admins |
| `cluster.pair_domain` (optional pattern, e.g. `{id}-t3.example.com`) | one agent's T3 for the desktop/mobile app | T3's own pairing only |
| `auth.tinyauth.domain` (tinyauth mode) | tinyauth's login page | anyone |

In `tailscale` mode there is one MagicDNS name: `domain` is served on 443 and the hub on `auth.hub_port` (default
8443), each by its own `tailscale serve` mapping onto its own ingress entrypoint; `pair_domain` isn't needed (apps on
the tailnet carry identity).

On `cluster.domain`, paths decide the tool:

| Path | Goes to (inside the chosen agent) |
|---|---|
| `/_agentlab/` | menu (served by the gate): your links, onboarding status; pick or switch among the agents you may open |
| `/_agentlab/accounts/` | Accounts app `:8790` (prefix stripped): JSON API + redirects; its UI is the hub's agent page. `/_agentlab/accounts/browser` is what "Browser" links to: the viewer while a browser is open, else a "no browser open" page |
| `/_agentlab/browser/` | noVNC `:6080` (prefix stripped; websocket at `/_agentlab/browser/websockify`) |
| `/_agentlab/files/` | the agent's file manager (`files-<id>` sidecar, File Browser, base URL `/_agentlab/files`, no auth of its own) |
| `/_agentlab/terminal/` | ttyd `:7681` (ttyd runs with `--base-path /_agentlab/terminal`, prefix NOT stripped) |
| everything else `/` | T3 `:3773` |

`/_agentlab/view/<id>?next=/path` (any agent you may open) sets the `agentlab_view` cookie; `/_agentlab/view/me` clears it.

## Onboarding and pairing

People use their own Claude / Codex accounts, so a new agent starts at onboarding, not T3:

1. **Onboarding** (the person's hub, `https://<hub_domain>/agents/<id>/onboarding`, backed by the agent's Accounts API): sign in to Claude Code and/or Codex (device-code flows), add connectors /
   MCP servers, optionally GitHub (`gh auth login` device flow). At least one AI sign-in is required to finish; the
   Accounts app records completion in `~/.config/agent/onboarded` and serves `GET /api/onboarding` → `{done, steps}`.
2. **The gate enforces it**: in pass 1, a request for T3 (`/` paths) on an agent whose onboarding isn't done gets a
   302 to `https://<hub_domain>/agents/<id>/onboarding` (the gate asks `http://agent-<id>:8790/api/onboarding`, caching `done`; admins
   viewing someone else are not redirected).
3. **"Open T3"** at the end of onboarding mints a one-time T3 pairing link (`t3 pair --ttl 5m`) for this browser and
   redirects to it on the same domain, so the browser gets its T3 session without copying anything.
4. **Pair the desktop or mobile app** (the person's hub, any time): mints a pairing link + QR code (`t3 pair`) whose host
   is where the app can reach this agent's T3:
   - `cloudflare-access` / `tinyauth`: this agent's `pair_domain` (e.g. `sara-t3.example.com`). Those hosts skip the
     browser sign-in (apps can't do it) and go straight to that agent's T3 (pass 1 router → strip headers → agent
     `:3773`, no gate), which only accepts paired sessions. `agentctl cloudflare setup` covers them with a separate
     Access application whose policy is Bypass. Without `pair_domain`, app pairing is unavailable and the page says
     why.
   - `tailscale`: the tailnet URL itself (identity comes with the connection).
   Paired devices are listed and revocable (`t3 auth session`).

## Companions the agent can change

Nobody orchestrates the cluster from outside, so each person's own agent (Claude / Codex in their T3) must be able to
customize its companions: add a feature, change the persona, remove a behaviour.

- **The code lives in the agent's workspace.** `agentctl apply` seeds `/workspace/companions/<name>/` (host:
  `<agent path>/workspace/companions/<name>/`) once from the repo's `companion/` as a git repo (initial commit
  "from agentlab <version>", branch `template` at that commit, remote `upstream` = the repo) and never overwrites it.
- **Template changes arrive as merge commits** (`agentctl apply`, so also every `agentctl update`): a changed
  `companion/` becomes a new snapshot commit on the checkout's `template` branch (git plumbing, the working tree is
  untouched), merged into the checked-out branch only when the tree is clean and the merge has no conflicts (a
  conflicted file whose template version already contains all of the checkout's changes to it counts as clean). Then
  the companion restarts and must come up (running, or "not configured"); if not, exactly that merge commit is undone
  and it restarts again. Conflicts are aborted and reported as "needs merging". Git runs as the checkout's owner, never
  root, and a checkout or `.git` that is a symlink is skipped. Results: `<data>/state/companions-template.json`,
  `<data>/companions/<name>/template.json` (the hub's `templateUpdate`), `update.json`, `agentctl status`.
- **The companion runs that code.** `agentlab/companion` is a base image (Python + the template's dependencies); the
  container mounts the checkout read-only at `/app` and runs it. If the checkout has `requirements.txt` changes, they
  are installed into a venv at `/data/venv` on start. A checkout that fails to start leaves the companion down and the
  error in its logs; it never affects other companions or agents.
- **The agent controls it without network access to shared services**, through files on its own disk (the host
  watcher acts on them; ownership is implied by the path, so an agent can only touch its own companions):
  - `~/.agentlab/requests/<action>~companion~<name>` with action `restart` (also picks up code and dependency
    changes), `stop`, `start`. The watcher deletes the file and writes the result to
    `~/.agentlab/results/<action>~companion~<name>.json`.
  - Logs: `/workspace/.companion/<name>/logs/companion.log` (rotated), status: `/workspace/.companion/<name>/status.json`
    (heartbeat, last error).
  - The image's `companion` command wraps all of it: `list | status | logs [-f] | test | create | remove | secret |
    settings | restart | stop | start` (`test` runs the checkout's tests inside the agent; `secret` reads the value
    from stdin only).
- **A companion belongs to its agent, and the agent fully controls it**: creates, customizes, configures and removes
  it, and the two hand work to each other through the companion bridge. There is no admin/agent split: every companion
  lives in `<data>/state/companions.json`; `[[companions]]` in `cluster.toml` only seeds one on the first apply that
  sees it (removed later by its agent → not recreated). Admins can do the same from the hub. Optional admin policy:
  `[companion_policy] self_service = false` turns agent actions off, `max_per_agent` (default 0 = no cap). Actions go
  through the same request files (created 0600 and renamed into place), payload in the file as JSON:
  - `create~companion~<name>` `{display_name, kind}`: the watcher checks the name is free cluster-wide and the cap,
    records it in `<data>/state/companions.json`, seeds the checkout, renders and deploys only that companion's stack.
    `cluster.json` lists every companion from the state file; the agent's live list is `~/.agentlab/companions.json`.
  - `remove~companion~<name>`: stops and removes its stack, moves its data dir to
    `<data>/companions/.removed/<name>-<date>`; the checkout in the workspace stays (it's the person's code).
  - `secret~companion~<name>` `{key, value}` with key in the companion's known secret names (`owner.txt`,
    `bot-token.txt`, `app-token.txt`, `user-token.txt`, `github-app-id.txt`, `github-app-key.pem`,
    `work-tools.md`): writes it 0600 into that companion's secrets dir. The request file is deleted right after
    reading, and the value never appears in results or logs. Secrets can't be read back, only replaced.
  - `settings~companion~<name>`: the payload is the settings object, merged into its settings.json (the same
    settings the hub edits).
  - `restart` / `stop` / `start` / `remove` carry `{at}`. Every action works only on companions of the requesting agent.
- **Slack app creation needs the person** (Slack has no API for it without an existing app token): `companion create`
  prints a prefilled "create app from manifest" link (manifest from the checkout's `slack-manifest.yml` with the display
  name), and the agent walks the person through installing it and pasting the two tokens to it, then sets them with
  `companion secret`.
- **Settings and secrets** can also be edited by the owner in their hub.
- The agentlab-managed `companion` skill (installed for Claude Code and Codex on every start) teaches the agent all of
  this; the instructions file only points at it.

## Your hub

The hub at `hub_domain` serves everyone with an agent, scoped to them:

- **People** see only their own agent (status, usage, disk, sign-ins, paired devices, onboarding) and their own
  companions (tasks, polls, PRs, settings, secrets, logs, restart). The hub enforces this server-side on every API
  from `X-Agentlab-User` / `X-Agentlab-Agent` (pass 2 headers), never from the client.
- **Admins** additionally see every agent and companion, and the cluster screens (Services, Configs, Storage,
  Secrets of the cluster, Notifications).
- The gate allows any verified user with an agent onto `hub_domain` (admins always); `coolify_domain` stays admins only.

## Config: `cluster.toml`

Lives at `/etc/agentlab/cluster.toml` (root, 0640). Full annotated example: [`cluster.example.toml`](../cluster.example.toml).
`agentctl` validates it and writes the resolved form to `<data>/rendered/cluster.json`, which is the ONLY config the
gate, hub, edge and host services read (mounted read-only). Shape of `cluster.json`:

```json
{
  "name": "example", "domain": "agents.example.com", "hub_domain": "agents-hub.example.com",
  "coolify_domain": "", "pair_domain": "{id}-t3.example.com", "timezone": "UTC", "data": "/srv/agentlab",
  "deploy": "coolify", "isolation": "sysbox", "publish_address": "127.0.0.1",
  "auth": {"mode": "cloudflare-access", "ingress": "cloudflared", "admins": ["admin@example.com"], "allow_domains": [],
           "cloudflare": {"team": "example", "audience": "<AUD tag>"}, "tinyauth": {"domain": ""}, "hub_port": 8443},
  "hub": {"publish": 0, "extra_stacks": [], "extra_secrets": {"folder": "", "map": "", "label": "Other secrets"}},
  "agents": [
    {"id": "sara", "owner": "sara@example.com", "memory": "12g", "cpus": 4, "upstream": "http://agent-sara",
     "hostname": "agent-sara", "image": "", "publish": {}, "path": "/srv/agentlab/agents/sara", "storage_unit": "",
     "subnet": "10.207.1.0/24", "pair_host": "sara-t3.example.com", "color": ""}
  ],
  "storage": {"mode": "shared", "pool_size": "", "pool_image": "/srv/agentlab/disks/pool.img", "person_size": "80g"},
  "limits": {"total_memory": "96g", "throttle": {"agent_gb": 12.0, "pool_gb": 96.0, "io_psi_max": 25}},
  "android": {"enabled": true, "system_image": "system-images;android-35;google_apis;x86_64"},
  "backups": {"enabled": true, "keep_days": 14, "time": "03:30"},
  "companions": [{"name": "helper", "display_name": "Helper", "agent": "sara", "kind": "slack"}],
  "companion_policy": {"self_service": true, "max_per_agent": 0}
}
```

Agent links are always `https://<domain>/...`; to open a specific agent, `https://<domain>/_agentlab/view/<id>?next=<path>`.

## Server layout

`data` defaults to `/srv/agentlab`.

```
/etc/agentlab/cluster.toml          the config (edit, then `agentctl apply`)
<data>/secrets/                     root 0700: cloudflare token, coolify token, per-agent secrets.env, companion secrets
<data>/disks/pool.img               shared mode with pool_size: one sparse ext4 image, mounted at <data>/agents
<data>/disks/<person>.img           per-person mode: one image per owner (slug of the email), mounted at <data>/people/<person>
<agent dir>                         home/ workspace/ linuxbrew/ — <data>/agents/<id> (shared) or <data>/people/<person>/<id>
                                    (per-person); cluster.json agents[].path is the resolved host path, use it everywhere
<data>/shared/android-sdk/          one Android SDK + system image, mounted read-only into every agent
<data>/companions/<name>/           a companion's data (companion.db, heartbeat, settings, venv); removed ones in .removed/
<data>/files/<id>/                  the agent's file manager config and database
<data>/state/                       agentctl's own state (companions.json, subnet numbers, seeded companions)
<data>/hub/                         hub state + watcher folder (usage, containers, events, requests)
<data>/backups/<YYYY-MM-DD>/        nightly backups (T3 databases, companion databases, config)
<data>/rendered/                    generated: cluster.json, compose/<stack>/docker-compose.yml, edge/dynamic.yml,
                                    firewall/agentlab.nft
```

## Containers and networks

| Container | Image | Networks | Notes |
|---|---|---|---|
| `agent-<id>` (alias) | `agentlab/agent` | `agentlab-<id>` | runtime `sysbox-runc` or unconfined opts; `cgroup_parent: agentlab.slice`; mem/cpu limits; `/dev/kvm` when Android is on; env `AGENT_ID`, `AGENT_OWNER`, `AGENTLAB_DOMAIN`, `AGENTLAB_HUB_DOMAIN`, `AGENTLAB_PAIR_HOST` (empty when none), `AGENTLAB_AUTH_MODE`, `AGENTLAB_ISOLATION`, `AGENTLAB_PUBLISHED` (`t3=7101,...`) and `AGENTLAB_PUBLISHED_HUB`, `ANDROID_ENABLED`, `ANDROID_SYSTEM_IMAGE`; `/dev/net/tun` in both modes; fixed IP `.2` in its subnet; the image has its own HEALTHCHECK; `[agents.publish]` (one-person setups) maps host ports |
| `files-<id>` | `gtstef/filebrowser:2.0.2-stable` | `agentlab-<id>` | in the agent's stack; uid 1000; mounts only that agent's `workspace` (and `home` read-only); config in `<data>/files/<id>` (not on the agent's disk); noauth behind the gate; heavy folders excluded from indexing only |
| `edge` | `traefik:v3.3.4` | `agentlab-edge` + every `agentlab-<id>` | entrypoints `ingress` :8088 (published `127.0.0.1:8088`; public ingress adds :80/:443), `routed` 127.0.0.1:8089; file provider `<data>/rendered/edge/` |
| `gate` | `agentlab/gate` | `agentlab-edge` + every `agentlab-<id>` | `:8080`, reads `cluster.json`; asks agents for onboarding state |
| `tinyauth` | `ghcr.io/tinyauthapp/tinyauth:v5.1.3` (≥ 5.1.3: fixes CVE-2026-77560) | `agentlab-edge` | tinyauth mode only |
| `hub` | `agentlab/hub` | `agentlab-edge` + every `agentlab-<id>` | `:8080`; mounts `rendered/` ro, `hub/watch`, `companions/`, `secrets/`, each agent's `path` at `/agents/<id>`, its state `<data>/hub/data` at `/data` (phone-push keys, display settings); optional `[hub] bark_url` / `bark_public` turn phone pushes on; `[hub] publish` (one-person setups) maps a host port and sets `HUB_PUBLISHED_OWNER`; `[hub] extra_secrets` mounts another host folder of secrets (admins only, its own group, its own map) |
| `companion-<name>` | `agentlab/companion` (base) | `agentlab-<agent id>` | runs the agent's checkout `/workspace/companions/<name>` mounted ro at `/app`; talks to its agent's Accounts bridge |

Ports inside an agent: 3773 T3, 8790 Accounts, 6080 noVNC, 7681 terminal; the files sidecar listens on 80.

Stacks (one Compose project / Coolify service each, so deploying one never restarts another): `agentlab-core`
(edge, gate, hub, tinyauth when used), `agentlab-agent-<id>`, `agentlab-companion-<name>`.

## Host services (systemd)

| Unit | What |
|---|---|
| `agentlab.slice` | memory cap for all agents together (`limits.total_memory`) |
| `agentlab-disks.service` | mounts the storage images (pool or per person) before Docker starts |
| `agentlab-throttle.service` | admission control for heavy jobs across all agents |
| `agentlab-watch.service` | always-on watcher: usage, containers, events, hub requests, agents' companion requests (within ~1 s) |
| `agentlab-firewall.service` | loads `<data>/rendered/firewall/agentlab.nft` (agents can't open connections to shared services or the host) |
| `agentlab-janitor.timer` | nightly: settled worktrees, package caches, agents' Docker leftovers |
| `agentlab-backup.timer` | nightly backups (`backups.time`), keeps `backups.keep_days`; only with `backups.enabled` |
| `agentlab-update.timer` | nightly `agentctl update --scheduled` at `updates.time`; only with `updates.agentlab = "daily"` |
| `cloudflared.service` | the tunnel (token in `<data>/secrets/cloudflare-tunnel.token`) |

## agentctl commands

See [`cli/README.md`](../cli/README.md) for the full list (`agentctl --help`). In short: `setup` (the guided way:
questions or flags, cluster.toml, then everything below in order), `secret set|list`, `init`, `doctor`, `install`,
`apply [--dry-run] [--stack S]`, `agent add|remove|list|adopt`, `companion create|remove`, `cloudflare setup`,
`backup run|list|restore`, `images build|pull`, `status`, `config [edit]`.

Privileges: commands that change the host re-run themselves through sudo (`sudo -n` without a terminal or with
`--json`; refused → exit 2, `result.needs = "sudo"`). Read-only ones run as the caller: members of the `agentlab`
group read `/etc/agentlab/cluster.toml` (root:agentlab 0640); `<data>/rendered` stays world-readable because the
gate and hub (non-root users) mount it, and holds no secrets; `<data>/secrets` and `<data>/backups` stay root-only.

Every command takes `--json` (one object: `{ok, exit, error, result, changes, messages, warnings}`) and exits 0
(done), 1 (failed) or 2 (stopped for a person: a token, a login link, or `--yes`). Only `setup` at a terminal and
`secret set` ask anything; with `--json` setup takes every answer as a flag and names any that are missing. `AGENTLAB_CONFIG` or `--config` overrides the
config path. Destructive commands (`agent remove` without `--keep-data`, `backup restore`) print what they will
delete and need `--yes`.

## Staying up to date

Two layers, both of which never cut off a running T3 turn by default:

- **Inside each agent**, the `updater` program (`image/agent-updater`) re-runs the entrypoint's installers
  (`image/tools.sh`) every `updates.agent_tools_hours` (env `AGENTLAB_UPDATE_HOURS`). The CLIs use new versions on
  their next run. T3 is a server, so when the installed T3 differs from the running one (its binary path,
  `~/.t3/runtime/versions/<v>/t3`), only the `t3` supervisord program restarts, and only while no run in T3's
  database is in progress (`orchestration_v2_projection_runs.status` not completed/cancelled/failed/interrupted).
- **The cluster**: `agentctl update` (by hand, or `agentlab-update.timer`) fast-forwards the repo (never merges or
  discards local changes), rebuilds or pulls the images, and runs `apply`. `apply` redeploys a stack when its file
  changed or when a running container's image is older than its local tag; an agent is only redeployed while idle
  (`--force` overrides). `update` then waits for busy agents, checking every 5 min for up to `updates.wait_hours`,
  updating each the moment it is idle; the core and companions never wait.
- **Each deploy finishes before the next step.** A stack is deployed at most once per run, and agentctl waits until
  every service of it runs in a container from this render (each service carries an `agentlab.rendered` label with the
  render's digest) before moving on. Coolify deploys in the background, so without this a second deploy could race
  the first. When a stack doesn't come up, the run fails with the containers' states and Coolify's view of the service;
  containers an interrupted run left behind (`<hash>_<name>`) are named so they can be removed.

When an agent is still busy at the end of the wait, `updates.on_busy` decides, for both layers (agents get it as
`AGENTLAB_ON_BUSY` and `AGENTLAB_UPDATE_WAIT_HOURS`): `defer` leaves it for the next run; `resume` notes the runs in
progress, restarts it, and once T3 answers again sends each chat whose run became `interrupted` the message "The
server restarted for an update; continue where you left off." (`t3 thread send`, as the companion bridge does).
The last run (time, commits, result, agents updated / deferred / chats resumed) is in `<data>/state/update.json`,
shown by `agentctl status` and `doctor` (a failed nightly run is a warning).
