---
name: companion
description: Create, set up, change, test, restart, debug and remove your companion bots (Slack bots that run next to you; their code lives in /workspace/companions). Use whenever the person mentions a companion, their Slack bot or "the bot", asks to set up a companion or a Slack bot, to add, change or remove a feature or behaviour of the bot, change its persona, fix it, read its logs or restart it.
---

# Your companion bots

A companion is your partner in Slack: a bot that runs in its own container next to you, on behalf of the person you
both work for. It's your front-end there. People talk to it, it hands real work to you (it starts and follows chats
in your T3 through the companion bridge), and it brings your answers back to Slack. You create it, its code is a git
repo in your workspace, and you control it with the `companion` command. You have no network path to the host or to
the companion's container; the command works through request files the host answers.

## Find out what you have

Never assume names:

```
companion list                 # your companions and how each is doing
companion status <name>        # heartbeat, version, last error
```

## Where things are

| What | Where |
|---|---|
| its code (a git repo) | `/workspace/companions/<name>/` |
| how to change it | `/workspace/companions/<name>/README.md`, section "Changing your companion" (read it first) |
| its log | `/workspace/.companion/<name>/logs/companion.log` (`companion logs <name>`, `-f` to follow) |
| its status | `/workspace/.companion/<name>/status.json` (`companion status <name>`) |
| template updates | the repo's `upstream` remote |

## Setting up a new Slack companion, end to end

Do these in order and tell the person what you're doing; steps 2-4 need them because Slack has no way to create an
app without a human.

1. **Create it.** Pick a short name with the person (lowercase, e.g. `helper`) and the name people will tag in Slack:
   `companion create helper --display-name "Helper"`.
   It prints the checkout path and a long `https://api.slack.com/apps?new_app=1&manifest_yaml=...` link. If the host
   refuses (for example the name is taken elsewhere on the cluster), tell the person what it said and pick another.
2. **The Slack app.** Give the person the link. They open it, pick their Slack workspace, check the summary and click
   Create. (The link already contains the right scopes, events and Socket Mode.)
3. **Install it.** In the new app's settings: "Install App" → "Install to <workspace>" → Allow. Then ask them to copy
   the **Bot User OAuth Token** (starts with `xoxb-`) from "OAuth & Permissions".
4. **App-level token.** "Basic Information" → "App-Level Tokens" → "Generate Token and Scopes", any name, add the
   scope `connections:write`, Generate, and copy the token (starts with `xapp-`).
5. **Store the tokens** as they paste them to you, one at a time. `companion secret` reads the value from stdin
   (`printf` is a shell builtin, so it never shows in the process list), and it's never shown again:
   ```
   printf '%s' 'xoxb-...' | companion secret helper bot-token.txt
   printf '%s' 'xapp-...' | companion secret helper app-token.txt
   ```
   Don't repeat the tokens back, write them to files, or commit them.
6. **The owner.** Ask the person for their Slack member ID (their profile → ⋯ → "Copy member ID", it looks like
   `U01ABCDEF`) and store it: `printf '%s' 'U01ABCDEF' | companion secret helper owner.txt`.
7. **Start it**: `companion restart helper`, then `companion status helper` and `companion logs helper`. When it's up,
   ask the person to DM it or tag it in a channel it was invited to (`/invite @Helper`).

Optional secrets, only when the person wants the feature: `user-token.txt` (the person's own read-only user token
`xoxp-`, from "OAuth & Permissions" → User OAuth Token, so it can see their DMs and threads), `github-app-id.txt` and
`github-app-key.pem` (a GitHub App, for pull request reviews), `work-tools.md` (notes about their tools). Settings:
`companion settings helper '{"key": "value"}'` (or `@file.json`); the README lists them.

## Changing it

1. Read the checkout's README ("Changing your companion") and the code you are about to touch.
2. Make the change. Keep it small; add or update tests in `tests/`.
3. `companion test <name>`: runs its tests here, in a venv of its own. Fix until they pass.
4. Commit: `git -C /workspace/companions/<name> commit -am "<what and why>"` (one commit per change, so it can be
   reviewed and rolled back).
5. `companion restart <name>`: the host restarts it with your code (a restart also installs changed requirements).
6. Check it came up: `companion status <name>` and `companion logs <name>`. A companion whose code fails to start
   stays down until it's fixed.
7. If it broke: `git revert HEAD`, `companion test <name>`, `companion restart <name>`, then find out what went wrong.

`companion stop <name>` / `companion start <name>` stop and start it without changing anything. Template updates:
`git fetch upstream`, merge or cherry-pick what you want, test, commit, restart.

## Settings and secrets

You can set them (`companion settings`, `companion secret`) but never read secrets back; the person can also edit both
in their hub (their agent's page → the companion). If a change needs a new setting or secret, add code that reads it
with a clear error when it's missing, then set it or tell the person what to set.

## Removing it

`companion remove <name>` stops it and removes it from the cluster (its data is kept aside by the host). Its code
stays in `/workspace/companions/<name>`; delete that folder only if the person asks. Also tell them to delete the
Slack app (api.slack.com → the app → "Delete App") if they won't use it again.
