# host

What runs on the server itself, outside containers. `agentctl install` puts it in place (units rendered from
`systemd/` with the cluster's paths); every service reads `<data>/rendered/cluster.json` (`$AGENTLAB_CLUSTER`).

| Folder | Unit | What |
|---|---|---|
| `throttle/` | `agentlab-throttle.service` | admits heavy jobs (installs, builds, tests) when the agent and the shared pool have room |
| `watch/` | `agentlab-watch.service` | the hub's hands: its buttons, the agents' companion requests, usage, inventory, network joins, secrets applied where used |
| `janitor/` | `agentlab-janitor.timer` | twice a day: Docker leftovers (a day unused), settled worktrees, package caches, scratch node_modules/venvs (2 days untouched); more caches and any unused image when storage is 70 % full |
| `bin/agentlab-mount-storage` | `agentlab-disks.service` | mounts the storage images before Docker starts |
| `install/` | | the numbered install steps (exit 2 = a manual step is needed) |
| `systemd/` | | unit templates, plus `agentlab.slice`, `agentlab-backup.*`, `agentlab-firewall.service`, `cloudflared.service` |
| `safe.py` | | file access inside agent-owned folders without following their symlinks |
| `fsm.py` | | the explicit state machine a job's state moves through (`watch/jobs.py`) |

Agents talk to the host only through files on their own disk: the throttle spool
(`~/.local/state/agent-throttle`) and `~/.agentlab/requests/<action>~companion~<name>` (results in
`~/.agentlab/results/`). Everything there is read and written through `safe.Folder`, because a root service that
follows an agent's symlink would let it read or overwrite any host file.

Tests: `cd host && python3 -m unittest discover -s tests`.
