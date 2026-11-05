# Looking after a cluster

`agentctl status --json` and `agentctl doctor --json` are the place to start; most problems show up there along with
their fix. Some checks need root to see (the secrets, the firewall): `sudo agentctl doctor --json` includes them.

## Someone can't get in

| What they see | Usually |
|---|---|
| Cloudflare, tinyauth or Tailscale turns them away | they're not an owner or admin in the config, or `apply` hasn't run since they were added; on a tailnet, its access controls |
| "Not available" from agentlab | they signed in with a different account than the one that owns the agent (check spelling and alias domains); on Cloudflare, `doctor` shows whether the Access application still matches |
| "No agent yet" | they may sign in but own no agent: `agentctl agent add` |
| Onboarding every time | they haven't finished it: one AI sign-in, then Finish, in their dashboard |
| The desktop or phone app won't connect | on Cloudflare or tinyauth `pair_domain` isn't set, or its DNS record is missing (`cloudflare setup` adds it); or the pairing link expired and needs a new one |

The gate logs every refusal with its reason: `docker logs` on the gate container.

## An agent isn't well

`status` names the check that fails (Accounts, terminal or T3). The container's logs come next, then the program's own
log inside it: `docker exec -u agent <container> tail -n 100 /home/agent/logs/<t3|accounts|terminal|dockerd>.log`.

A first start downloads Claude Code, Codex and T3 into the agent's home, so it takes a few minutes; `apply` and
`setup` wait for it and `doctor` shows it as still starting. Every download gives up on a stall and retries, so an
agent that stays starting for more than 20 minutes is stuck on something else: its `docker logs` say what, and a
restart usually clears it. With Coolify, a new agent first waits until it's off Coolify's own network (its log says
so); that takes seconds.

If it's memory, the dashboard's agent page shows usage. Heavy jobs wait their turn in the throttle (`journalctl -u
agentlab-throttle`) rather than all running at once; raise an agent's `memory` only when the machine has room under
`limits.total_memory`. Restarting an agent (dashboard → agent → Restart, or `docker restart`) keeps its chats and
files.

## Disk space

`status` shows each disk: the shared pool, or each person's. The janitor tidies nightly and whenever a disk passes
75%: settled worktrees (clean, pushed, idle 12 hours or more), package caches, and the agents' Docker leftovers. A
person's full disk only stops that person; tell them, or raise `person_size` (disks grow, never shrink) and `apply`.
Nothing inside someone's workspace gets deleted without asking them or the admin.

## Companions

A companion's code belongs to its agent (`<agent path>/workspace/companions/<name>/`, a git repo); the agent changes
and restarts it with its `companion` command, so you normally leave it alone. If one is down after a change, its log is
in `<agent path>/workspace/.companion/<name>/logs/companion.log` with `status.json` beside it; let the owner know, and
their agent can revert and restart. "Not configured" means its Slack secrets are missing: the owner adds them in their
dashboard, or an admin with `agentctl secret set companion/<name>/bot-token.txt` (and `app-token.txt`).

Template updates arrive on their own: every `apply` and `update` merges a changed companion template into each
checkout as a commit, restarts the companion, and undoes that merge if it then won't start. `agentctl status` lists
the ones that aren't current: `skipped` means the agent had uncommitted work (tried again next time), `conflict` means
the agent needs to merge it (`git merge template`, resolve, test, commit, restart), and `reverted` means the merged
code didn't start (the error is in the line and the companion's log). Don't merge or reset someone's checkout
yourself.

## After a crash or reboot

On Linux, systemd brings everything back: the storage images mount, then Docker restarts every container. On WSL,
Windows has to start the distro first, so `apply` registers a Windows task (`\agentlab\Autostart`) that starts it at
boot and again within 15 s whenever it stops: a crash, Windows killing WSL when RAM runs out, a `wsl --shutdown`. It
backs off to every 5 minutes while the distro keeps failing; its log is `%LOCALAPPDATA%\agentlab\autostart.log`.

- Registering it to start at boot needs admin: run `apply` once from a WSL terminal opened as administrator.
  Otherwise it starts when you sign in to Windows, and `doctor` says which.
- To keep WSL down on purpose (to compact or copy its disk), stop the task first:
  `Stop-ScheduledTask -TaskPath '\agentlab\' -TaskName Autostart`.
- If something else already starts the distro (your own boot task), set `[cluster] wsl_autostart = false`.

## Backups

Each night at `backups.time` agentlab keeps the T3 databases, the companion databases and the config, for
`keep_days`. They live on the same machine, so for real disaster recovery copy `<data>/backups/` somewhere else.

## Updates

`agentctl update` pulls the repo (only fast-forward: it stops on local changes rather than merging), rebuilds the
images and applies. Agents restart only when something they run changed, and never mid-turn: a busy agent is waited
for up to `[updates] wait_hours`, then `on_busy` decides between `defer` (next time) and `resume` (restart it; T3
picks the cut-off turns back up by itself). `agentctl update --resume` skips the wait and resumes busy agents straight away.
`agentctl status` shows the last run.

- Nightly updates: set `[updates] agentlab = "daily"` and run `agentctl install --only units`; `"off"` stops them. A
  failed night shows in `doctor`.
- Inside each agent, T3, Claude Code and Codex keep themselves current every `agent_tools_hours` (0 turns that off),
  and a new T3 goes live at the next idle moment; the agent's `~/logs/updater.log` has the details.
- In a hurry while someone's mid-turn: `agentctl apply --force` restarts them anyway, after you've warned them.
- `update` needs the repo on the server to be a git clone; a copied folder can't be pulled.
- A deploy that doesn't come up stops the run with each container's state. Old containers named `<hash>_<name>`
  are leftovers from an interrupted deploy: `docker rm` them and run `agentctl apply` again.

## Before installing

`agentctl install` (and so `setup`) first checks that this host has what every step needs: apt with the packages it
installs, a kernel Sysbox runs on, `/dev/kvm` and a Java 17+ runtime for Android. If anything is missing it stops
before changing the host and says what to fix; `agentctl doctor` shows the same checks any time. Java is whichever of
21, 25 or 17 the distro carries (Debian 13 has 21 and 25, Ubuntu 24.04 has 17 and 21).
