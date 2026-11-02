---
name: agentlab
description: Install, upgrade and operate an agentlab cluster (private AI coding agents per person, with sign-in, hub and companions) on a Linux server over SSH. Use when asked to set up agentlab, add or remove people or agents, change access or storage, debug a cluster, or upgrade it.
---

# agentlab

You are setting up or running an agentlab cluster on a server you reach over SSH. `agentctl` on the server does the
work; you decide the order, read its JSON, and handle what it can't do alone (human steps). Read
`docs/architecture.md` in the repo once before the first install: it is the contract for how everything fits.

## Ground rules

- **Drive `agentctl` with `--json`** and act on the result, not on prose. Exit codes: `0` done, `1` failed (read the
  error, fix, retry), `2` needs a human step or a confirmation (show the human exactly what and wait).
- **Never pass `--yes` on your own.** Destructive commands (`agent remove` without `--keep-data`, `backup restore`)
  print a plan and stop; show the plan to the human and only re-run with `--yes` after they say so.
- **Always `--dry-run` first** for `apply` and `cloudflare setup` on a cluster that already serves people, and show
  the plan if it restarts anyone's agent.
- **Secrets never go in chat, git, or command lines.** Ask the human to put them in the file `doctor` names (e.g.
  `<data>/secrets/cloudflare-api.token`) with `sudo install -m 600 /dev/stdin <file>` and paste into the terminal.
- **One change at a time on a live cluster**, then `agentctl status --json` to confirm before the next.
- Use `sudo` for `agentctl` (it manages systemd, Docker, disks and the firewall).

## Install, from zero

Ask the human these first (they decide the whole shape; don't guess):

1. **How do people reach it?** → `auth.mode` (see [access.md](references/access.md)):
   `cloudflare-access` (company already on Cloudflare; Google sign-in at Cloudflare's edge),
   `tailscale` (everyone is on one tailnet), or `tinyauth` (no Cloudflare Access; Google sign-in on the server).
2. **Domain names** (first-level, e.g. `agents.example.com`, `agents-hub.example.com`) or, for tailscale, the
   machine's MagicDNS name.
3. **Who:** admin emails, and each person's email with how many agents they want.
4. **Storage:** `shared` (one pool; simplest) or `per-person` (a capped disk per person; for shared servers where one
   person must not fill the disk for everyone). Sizes against the server's free disk.
5. **Isolation:** `sysbox` for anything more than one person on a real Linux host; `unconfined` only for one person or
   WSL.
6. **Deploy:** `coolify` (they want a UI for stacks) or `compose`.
7. Android emulator (needs `/dev/kvm`), companions (Slack bots), backups time.

Then:

```sh
git clone <repo> /opt/agentlab && cd /opt/agentlab
sudo ./cli/agentctl doctor --json            # host facts; nothing changes
sudo install -D -m 640 cluster.example.toml /etc/agentlab/cluster.toml   # then edit it with the answers above
sudo ./cli/agentctl doctor --json            # now also checks the config
sudo ./cli/agentctl install --json           # Docker, Sysbox, ingress tools, units, firewall, images
```

Read every `doctor` check with `ok: false`: `fix` is either a command you run or a manual step for the human.
Then the access mode's own steps from [access.md](references/access.md), then:

```sh
sudo ./cli/agentctl apply --dry-run --json   # show the plan
sudo ./cli/agentctl apply --json
sudo ./cli/agentctl status --json            # every agent running and healthy
```

**Verify like a user**, not just by status: open the domain signed in as an admin (the human does this), check the
menu lists the agents, the hub loads, and a test person lands on onboarding. Then tell each person their URL and
that the admin can see their agent.

## Day-to-day

| Ask | Do |
|---|---|
| Add a person / agent | `agentctl agent add <id> <email> --json`, then `apply` (it also updates the sign-in allow list where it can) |
| Remove an agent | `agentctl agent remove <id> --keep-data` (safe); without `--keep-data` show the plan, wait for yes |
| Someone's T3 threads are gone | `agentctl backup list --json`, show the dates, `backup restore <date> <agent>` after yes |
| Disk nearly full | `status` shows the storage unit; the janitor runs nightly; look at the biggest agents in the hub's Storage screen before deleting anything, and ask |
| Upgrade | `git pull`, `agentctl images build`, `apply --dry-run`, then `apply`. Companion checkouts in agents' workspaces are theirs: never overwrite them; tell owners the template has updates (`git fetch upstream` in their checkout) |
| Change access mode | Plan it with the human: it changes how everyone signs in. Follow both modes' sections in access.md |

Troubleshooting: [operate.md](references/operate.md).

## What you must not do

- Don't edit anything inside an agent's home or workspace except through `agentctl` (it's that person's machine).
- Don't read people's T3 chats, code or credentials while debugging unless the human asks for that specific thing.
- Don't open ports, disable the firewall table `agentlab`, or switch `isolation` to `unconfined` to "make it work".
- Don't put company secrets (vaults, production credentials) into agents or companions unless the human says which
  and where.
