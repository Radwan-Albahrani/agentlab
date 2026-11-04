# Agent image

One image for every agent (`agentlab/agent`). `agentctl apply` runs one container from it per person; see
[docs/architecture.md](../docs/architecture.md) for how it is wired into the cluster.

Build: `image/build.sh` (or `TAG=agentlab/agent:test image/build.sh`).

## What's inside

| Program (supervisord) | Port | What |
|---|---|---|
| `t3` | 3773 | T3 Code: the agent's chats (Claude Code, Codex) |
| `accounts` | 8790 | Accounts page API: sign-ins, connectors, env vars, pairing links, the hub card, the companion bridge |
| `terminal` | 7681 | ttyd web terminal (herdr, or `?arg=shell` for tmux), base path `/_agentlab/terminal` |
| `xvfb` `vnc` `novnc` | 6080 | virtual display :99 and its noVNC viewer; on only while a browser or the emulator is open |
| `docker-proxy` `dockerd` | | the agent's own Docker engine (root under Sysbox via one sudo rule, rootless otherwise; see `agent-dockerd`), started on first use, stopped after 15 idle minutes |
| `android` `android-reaper` | | Android emulator on demand (`android-emulator start`), stopped after 30 minutes without adb use |
| `browser-reaper` | | closes an idle Chrome and turns the display off |
| `updater` | | refreshes T3, Claude Code, Codex and the other CLIs every `AGENTLAB_UPDATE_HOURS` (`agent-updater`, installers in `tools.sh`); restarts only `t3`, only while idle (`AGENTLAB_UPDATE_WAIT_HOURS`, `AGENTLAB_ON_BUSY`) |
| `janitor` | | stops orphaned processes that sat idle (forgotten dev servers, browsers) |
| `shim-sync` | | keeps the throttle shims in front of the heavy tools that are installed |
| `herdr`, `cyrus` | | terminal multiplexer; Linear agent (off until configured) |

Skills: `skills/companion` is installed on every start into `~/.claude/skills/` and `$CODEX_HOME/skills/` (default
`~/.codex/skills/`), marked `.agentlab-managed`; a same-named folder without that marker is left alone.

Commands for the agents: `android-emulator` (start/stop/status/wipe) and `companion` (list/status/logs/test/restart/
stop/start the companions whose code lives in `/workspace/companions/<name>`; start/stop/restart are requests the
host's watcher answers through `~/.agentlab/requests/` and `~/.agentlab/results/`).

Accounts API (the hub draws the UI): sign-ins and connectors (`/api/page`, `/api/state`, `/api/act`), env vars,
`GET /api/onboarding` + `POST /api/onboarding/finish` (needs one AI sign-in; writes `~/.config/agent/onboarded`),
`POST /api/pair {kind: browser|app, label}` (one-time T3 pairing link), `GET /api/devices`, `POST /api/devices/revoke
{id}`, `/api/summary`, and the companion bridge.

Claude Code, Codex, T3, herdr, Playwright MCP, mcp-remote and the EAS CLI are installed into the home volume on first
start and updated daily in the background, so the image itself rarely changes. Homebrew installs into
`/home/linuxbrew`.

The Accounts page has no login of its own: the edge's gate checks every request (Cloudflare Access JWT + the agent's
owner) and each agent sits alone on its own Docker network, so nothing else can reach it. The companion bridge
(`POST /api/t3/*`) additionally needs the key in `~/.config/agent/bridge-key` (header `X-Agent-Key`).

Heavy commands (installs, builds, tests) pass through the throttle shim (`throttle/`), which waits for the host's
broker to admit them; the spool lives in `~/.local/state/agent-throttle/`.

## Environment

| Variable | Set by | Meaning |
|---|---|---|
| `AGENT_ID` | compose (required) | the agent's id |
| `AGENT_OWNER` | compose | the owner's email, shown on the Accounts page |
| `AGENTLAB_DOMAIN` | compose | the cluster domain people reach their agent on (links, pairing) |
| `AGENTLAB_HUB_DOMAIN` | compose | the hub's domain (the Accounts page's `/` redirects there) |
| `AGENTLAB_ISOLATION` | compose | `sysbox` or `unconfined`: which Docker engine the agent gets (see `agent-dockerd`) |
| `AGENTLAB_AUTH_MODE` | compose | `cloudflare-access`, `tailscale`, `tinyauth` or `none` (app pairing depends on it) |
| `AGENTLAB_PAIR_HOST` | compose | this agent's host for the T3 app (empty: app pairing unavailable, except on a tailnet) |
| `AGENTLAB_COMPANIONS` | compose | comma list of this agent's companions (the `companion` command, the instructions) |
| `ANDROID_ENABLED` | compose | `1` to offer the emulator (also needs `/dev/kvm` and the shared SDK) |
| `ANDROID_SYSTEM_IMAGE` | compose | SDK package of the phone image, default `system-images;android-35;google_apis;x86_64` |
| `TZ` | compose | time zone |
| `DOCKER_IDLE_MINUTES`, `BROWSER_IDLE_MINUTES`, `ANDROID_IDLE_MINUTES`, `JANITOR_IDLE_MINUTES` | optional | idle timeouts |

## Volumes and devices

| Path | What |
|---|---|
| `/home/agent` | the agent's home: sign-ins, T3 chats (`~/.t3/userdata`), tools, logs, `~/.android` |
| `/workspace` | repos |
| `/home/linuxbrew` | Homebrew |
| `/opt/android-sdk` (read-only) | the shared Android SDK from `<data>/shared/android-sdk` (when Android is on) |
| `/dev/kvm` | for the emulator; the agent user (uid 1000) must be able to read and write it |

Isolation: under `sysbox-runc` no extra options are needed; under `unconfined` (WSL) the container needs
`seccomp=unconfined`, `apparmor=unconfined`, `systempaths=unconfined` and `/dev/fuse` + `/dev/net/tun`. Give it
`shm_size: 1gb` for Chrome.

## Tests

`python -m pytest image/tests` (needs bash for the shim tests).
