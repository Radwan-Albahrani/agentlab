<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/banner-dark.svg">
    <img alt="agentlab: AI coding agents that live on your own machine" src="docs/assets/banner-light.svg" width="100%">
  </picture>
</p>

<p align="center">
  <b>Your own always-on AI coding agents, on a machine you own.</b><br>
  Claude Code and Codex with a real browser, Docker, a terminal and a phone emulator.<br>
  Use it alone on a home server, or share one box with friends, family or your team.
</p>

<p align="center">
  <a href="#get-started">Get started</a> ·
  <a href="#what-you-get">What you get</a> ·
  <a href="#sharing-it">Sharing it</a> ·
  <a href="docs/architecture.md">How it works</a>
</p>

---

## Why

AI coding agents are at their best when they never stop: a long refactor that runs overnight, a test suite that takes
an hour, a pull request reviewed while you sleep. Your laptop has to stay open for that, and your laptop is also the
thing you want to close.

**agentlab moves your agents onto a machine that stays on**: a home server, an old PC, a Windows machine with WSL, or a
rented box. Start something from your desk, close the lid, check on it from your phone. If other people use the same
machine, each of them gets their own private space.

## What you get

<table>
<tr>
<td width="50%" valign="top">

### 🧠 Agents that keep going
Your chats and their work live on the machine in [T3](https://github.com/pingdotgg/t3code), not in a browser tab.
Walk away mid-task and it carries on. Pick it up from the desktop app or your phone.

</td>
<td width="50%" valign="top">

### 🔑 Your own AI accounts
Sign in once with your own **Claude** or **Codex** subscription and connect the tools you use (GitHub, Linear,
Notion…). Nothing is shared unless you share it.

</td>
</tr>
<tr>
<td valign="top">

### 🛠️ A real workshop
Each agent drives a **Chrome** you can watch live, runs **Docker** for databases and tests, and has a **terminal**, a
**file manager** and an **Android emulator** for trying mobile apps.

</td>
<td valign="top">

### 🗂️ As many agents as you like
Separate agents for work, side projects and experiments, each with its own files, accounts and settings. Switch
between them from one place.

</td>
</tr>
<tr>
<td valign="top">

### 🌱 A companion in Slack
Give an agent a Slack bot that works with it: takes requests, runs polls, reviews pull requests with screenshots,
posts updates. Tell your agent *"add a standup command to my bot"* and it changes the bot itself.

</td>
<td valign="top">

### 📊 One dashboard
Usage, storage, paired devices and your bots, in one place. It quietly keeps the machine healthy too: queues heavy
jobs, cleans up old work, backs up your chats every night.

</td>
</tr>
</table>

## Sharing it

One machine can host agents for several people: a household, a group of friends, a study group, a team.

- 🔐 **Everyone signs in.** Through Tailscale, Cloudflare (Google, Microsoft or an email code), or a Google login on the
  machine itself. Only people you've listed get through.
- 🚪 **Everyone gets their own room.** Each person's agents are sealed off: nobody can see anyone else's files, chats or
  logins, and every request is checked on the machine, not just at the door.
- 💾 **Nobody can sink the ship.** Each person can get their own disk space, heavy jobs wait their turn instead of
  freezing the machine, and chats are backed up nightly.
- 👀 **Whoever runs the machine can see everything.** That's how they help when something breaks, so make sure
  everyone knows who that is.

## Get started

### The easy way: let an AI agent set it up

Give Claude Code or Codex access to the machine (a terminal on it, or SSH) and say:

> *Set up agentlab from https://github.com/Radwan-Albahrani/agentlab using its skill.*

It follows the [bundled skill](skills/agentlab/SKILL.md), asks you the few things only you know (how you'll reach it,
who gets an agent), does the rest, and stops for your yes before anything it can't undo.

### The hands-on way

```sh
git clone https://github.com/Radwan-Albahrani/agentlab.git && cd agentlab
cli/agentctl init            # one-time: puts agentctl on your PATH
agentctl config edit         # who gets an agent, and how you'll reach it
agentctl doctor              # tells you what's missing and exactly how to fix it
agentctl install             # sets up the machine
agentctl apply               # brings your agents to life
```

That's the whole loop: change the config, run `agentctl apply`. A new agent is one line:

```sh
agentctl agent add side-project you@example.com && agentctl apply
```

How to reach it from anywhere, step by step (Tailscale is the simplest for one person):
[access guide](skills/agentlab/references/access.md).

## What you need

- A Linux machine with Docker, or Windows with WSL. Ubuntu 24.04 is what it's built on.
- Roughly **12 GB of memory and 30–60 GB of disk per busy agent**. A 32 GB home server runs two or three comfortably.
- A way to reach it: **Tailscale** (free for personal use), **Cloudflare**, or a domain pointing at the machine.
- Sharing with others on one machine needs a regular Linux install (not WSL) for the strongest separation.

## Status

agentlab is **early**. Every part is tested and the whole system has run end to end, but a few pieces haven't been
proven on real hardware yet: the strongest separation mode (Sysbox), the Android emulator, live Cloudflare / Tailscale
sign-in, and Coolify deploys. `agentctl doctor` checks each of them; if something breaks, please open an issue.

<details>
<summary><b>For the curious: what's inside</b></summary>

<br>

| Folder | What it is |
|---|---|
| [`cli/`](cli/README.md) | `agentctl`, the one command that sets up and runs everything |
| [`image/`](image/README.md) | what each agent runs: T3, Claude Code, Codex, Chrome, Docker, Android |
| [`gate/`](gate/README.md) | the sign-in check in front of every request |
| [`hub/`](hub/README.md) | the dashboard |
| [`companion/`](companion/README.md) | the Slack companion |
| [`host/`](host/README.md) | the background services that keep the machine healthy: memory, disk, backups, firewall |
| [`skills/agentlab/`](skills/agentlab/SKILL.md) | the instructions an AI agent follows to set it up and run it |
| [`docs/architecture.md`](docs/architecture.md) | the full technical design |

Working on agentlab itself? `scripts/check.sh` runs every test with nothing but Docker installed.

</details>
