---
name: agentlab
description: Install, upgrade and operate an agentlab cluster (private AI coding agents per person, with sign-in, hub and companions) on a Linux server over SSH. Use when asked to set up agentlab, add or remove people or agents, change access or storage, debug a cluster, or upgrade it.
---

# agentlab

You're setting up or looking after an agentlab cluster on a server you can reach over SSH. `agentctl` on the server
does the work. Your job is to pick the order, read what it reports, and bring in the person you're working for only
when something genuinely needs them: a token they create, a link they open, a yes to something that can't be
undone. If you want the full picture of how the parts fit, `docs/architecture.md` in the repo has it.

## How to drive agentctl

Add `--json` to every command and act on the result rather than the prose. The exit code tells you what happened: `0`
means done, `1` means it failed (the error says why; fix it and try again), and `2` means it stopped for a person or
a confirmation, with the exact ask in the error.

Don't put `sudo` in front of it. Commands that change the server re-run themselves through `sudo -n`, and read-only
ones (`doctor`, `status`, `config`, `agent list`) run as you. If sudo wants a password you'll get exit 2 with
`result.needs = "sudo"` and the command to run: ask the person to run it, or to allow passwordless sudo for agentctl
(the error includes the sudoers line).

A few rules keep people's work safe:

- `--yes` is theirs to give. Anything that deletes (an agent's data, a restore over current chats) prints its plan and
  stops; show them the plan and only re-run with `--yes` once they agree.
- On a cluster people already use, run `apply --dry-run` and `cloudflare setup --dry-run` first, and mention it if
  the plan restarts someone's agent.
- Secrets never pass through you, a chat or a command line. When one is needed, ask the person to run
  `agentctl secret set <name>` in a terminal on the server: it prompts without echoing and saves it in the right
  place. `agentctl secret list --json` tells you which are saved.
- On a live cluster, make one change at a time and check `agentctl status --json` before the next.

## Setting it up

The quickest route is the guided setup, which takes every answer as a flag when you drive it:

```sh
git clone https://github.com/Radwan-Albahrani/agentlab.git /opt/agentlab
/opt/agentlab/cli/agentctl setup --json --reach <me|tailnet|cloudflare|tinyauth> --admin <email> [...]
```

Ask the person first; these choices shape everything and aren't yours to guess:

- **How people will reach it.** For one person, `--reach me`: plain ports on their own tailnet or LAN, nothing to
  set up. For a group on one tailnet, `tailnet`. For a company on Cloudflare, `cloudflare`, and ask which network:
  `--network private` (the default: only devices on the company's Cloudflare One client reach it, no public address)
  or `--network public` (a public Cloudflare sign-in page). Without either, `tinyauth` (a Google sign-in page on the
  server). [access.md](references/access.md)
  explains each.
- **The address** (`--domain`, and `--hub-domain` for the dashboard). On Cloudflare keep both one level under the zone
  (`agents.example.com`, `agents-hub.example.com`). For `me` and `tailnet` the machine's own name is the default.
- **Who gets agents** (`--people "sara@example.com=2, omar@example.com"`; for `me`, `--agents "work, personal"`). The
  admin is a person too: ask how many agents they want for themselves, since being admin only adds the right to open
  everyone else's.
- Optionally: `--storage per-person` (a capped disk per person, the default when several people share it),
  `--android` / `--no-android`, `--allow-domains example.com` (anyone at that domain may sign in, only owners get an
  agent), `--deploy coolify` (if they want Coolify's UI; plain Docker Compose is the default).

Setup writes `/etc/agentlab/cluster.toml`, then installs everything, sets up Cloudflare when chosen, and starts the
agents. When it stops with exit 2 it's waiting on a person: a Cloudflare API token to save (`agentctl secret set
cloudflare-api`), a Tailscale login link to open, a Coolify token to create. Pass the ask on word for word, wait for
them, and run `agentctl setup --json` again; it picks up where it stopped and keeps the config it already wrote.
Setup fetches the latest agentlab itself each time, so there's nothing to pull first. If an exit-2 message only asks
for an `agentctl` command, that's an agentlab bug: run it yourself, carry on, and open an issue.

When it's done, check it the way people will use it: the admin opens the address, sees the agents on the menu, the
dashboard loads, and a new person lands on onboarding. Then tell everyone their address, and that the admin can see
their agent.

If someone prefers to edit the config by hand, the long way still works: `agentctl init`, edit
`/etc/agentlab/cluster.toml` (every key is explained in `cluster.example.toml`), `agentctl doctor`, `agentctl
install`, `agentctl cloudflare setup` when using Cloudflare, `agentctl apply`.

## Day to day

| They ask for | You run |
|---|---|
| A new person or agent | `agentctl agent add <id> <email> --json`, then `apply` (their sign-in is allowed with it) |
| Removing an agent | `agentctl agent remove <id> --keep-data` is safe; deleting the data needs their yes on the plan |
| Lost chats | `agentctl backup list --json`, show the dates, then `backup restore <date> <agent>` once they say yes |
| A full disk | `status` shows each disk; the janitor tidies nightly; look at the biggest agents in the dashboard's Storage screen and ask before deleting anything |
| Room for one more person | With per-person disks, `person_size = "auto"` (or a lower size) and `apply`: the others shrink safely, never below their data; `apply --dry-run` first, since a shrink stops that person's agents for a few minutes ([operate.md](references/operate.md#disk-space)) |
| An upgrade | `agentctl update --json` (pull, rebuild, apply; busy agents are waited for). Companion code in agents' workspaces belongs to them; template changes reach it as merge commits on its own |
| A different sign-in | Plan it with them first, since it changes how everyone gets in; [access.md](references/access.md) covers each way |

When something's off, [operate.md](references/operate.md) has the usual causes.

## Off limits

- Anything inside an agent's home or workspace, except through agentctl: it's that person's machine.
- People's chats, code or logins, unless the person you work for asks for that specific thing.
- Opening ports, disabling the `agentlab` firewall table, or switching `isolation` to `unconfined` to make something
  work.
- Company secrets (vaults, production credentials) in agents or companions, unless you're told which and where.
