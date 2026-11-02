# Operating and troubleshooting

Start every investigation with `sudo agentctl status --json` and `sudo agentctl doctor --json`; most problems show up
there with a `fix`.

## Someone can't get in

| Symptom | Look at |
|---|---|
| Cloudflare / tinyauth / Tailscale refuses them | they're not an owner or admin in `cluster.toml`, or `apply` hasn't run since they were added; tailscale: the ACL |
| Gate page "not available" (403) | signed in as a different account than their `owner` (check case and alias domains); cloudflare: AUD in config doesn't match the Access app (`doctor`) |
| "No agent yet" | they're allowed in but own no agent: `agentctl agent add` |
| Redirected to onboarding every time | they haven't finished it: at least one AI sign-in + Finish in their hub |
| Desktop/mobile app can't connect | `pair_domain` unset (cloudflare/tinyauth), DNS for their pair host missing (`cloudflare setup`), or the pairing link expired (make a new one in the hub) |

The gate logs every refusal with the reason: `docker logs <gate container>`.

## An agent is unhealthy

1. `status` shows which check fails (Accounts, terminal, T3).
2. `docker logs <agent container>`, then inside: `docker exec -u agent <agent> tail -n 100 /home/agent/logs/<program>.log`
   (t3, accounts, terminal, dockerd, docker-proxy).
3. Out of memory: the hub's agent page shows usage; heavy jobs queue in the throttle (`journalctl -u agentlab-throttle`)
   rather than run at once; raise the agent's `memory` only if the host has room under `limits.total_memory`.
4. Restart one agent: hub → agent → Restart, or `docker restart <agent>`. Its chats and files survive restarts.

## Disk

- `status` shows each storage unit (the pool, or each person's disk). The janitor (nightly, and at 75%+) removes
  settled worktrees (clean, pushed, idle 12 h+), package caches and agents' Docker leftovers.
- A per-person disk full only stops that person; tell them, or raise `person_size` (grows, never shrinks) and `apply`.
- Never delete inside someone's workspace without asking them or the admin.

## Companions

- Code is the owner's: `<agent path>/workspace/companions/<name>/` (git). Their agent changes it and restarts it with
  the `companion` command; you normally don't touch it.
- Down after a change: logs at `<agent path>/workspace/.companion/<name>/logs/companion.log`, status in `status.json`
  next to it. Tell the owner (their agent can `git revert` and `companion restart`).
- "not configured": its Slack secrets are missing — the owner adds them in their hub (Secrets).

## Backups

Nightly at `backups.time`: T3 databases, companion databases, the config, kept `keep_days`. They are on the same
server: for real disaster recovery, ask the human where to copy `<data>/backups/` off-machine.

## Upgrades

`git pull` in the repo, `agentctl images build`, `apply --dry-run` (shows which stacks restart), `apply`. Agents
restart only if their image or settings changed; people lose nothing but running processes, so warn them first.
