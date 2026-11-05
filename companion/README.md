# Companion

A Slack bot that is one person's agent in Slack. It lives in that person's agent environment: every task it takes
becomes a T3 chat in their agent, and the chat's progress and answer come back to the Slack thread. Only the owner
gives it work; anyone else who addresses it gets one polite refusal.

What it does:

- **Tasks.** Tag it (`@Companion fix the flaky login test`) or DM it, and it starts a T3 chat with the whole thread
  as context. Reply in the thread to continue. It shows live progress, retries when the model is busy, and splits
  big work into T3 child threads. Replies and files (screenshots, documents) go into that thread. Settings →
  "People who can tag it" lets colleagues give it work too; their sensitive steps wait for your Approve.
- **Errands.** Tag it bare on someone else's message and it handles their request as you (find a document, give
  access, look something up). Anything sensitive (access, money, deleting, sharing) waits for your Approve; replies to
  them wait for your Send. Team mode also notices colleagues asking you directly; dry-run mode lets you rehearse.
- **Posts, DMs and polls.** The agent never posts itself: it writes a file and the companion previews it for you,
  then posts it, DMs the people you named, or runs a poll (buttons, live count, closing on time, the winner).
- **Product-update drafts.** Drafts the agent prepares are previewed in your DM; reply to revise, tap to post, and a
  revision of a posted update edits the post in place.
- **Pull request review and QA.** From the hub's Pull requests tab or Slack (`@Companion <PR link>`, or "review"
  under a message linking a PR). A lead T3 chat reviews in lanes and runs the app to QA it, then the companion posts
  one review as its GitHub App: findings on their lines (one-click suggestions when small), a QA comment with
  screenshots, and on a re-review it edits its own comments and resolves the threads that were fixed.

Everything it does is shown on the hub (task cards, events, polls, pull requests, settings).

## How it is wired

```
Slack (Socket Mode, outbound only) ──► companion ──► http://agent-<id>:8790/api/t3/*   (the agent's Accounts bridge)
                                           │  runs   /app    = the agent's checkout /workspace/companions/<name> (read-only)
                                           │  reads  /t3     = the agent's ~/.t3/userdata (progress, answers)
                                           │  writes /files  = the agent's /workspace/.companion (its own <name>/ folder:
                                           │                   attachments, outboxes, drafts, logs, status.json)
                                           └─ writes /data   = <data>/companions/<name>/ (what the hub reads, the venv)
```

`agentlab/companion` is only a base image: Python, this template's dependencies and a launcher (`base/run.py`). The
code that runs is the owner's agent's git checkout of this folder, so the agent can change its companion. On start
the launcher:

- stays down quietly (exit 0, status "not configured") while a required Slack secret is missing;
- installs a changed `requirements.txt` into `/data/venv` (on top of the image's packages); a failed install exits 1
  and the container's on-failure restart policy backs off;
- runs `python -m bot`, writing its output to `docker logs` and to `/files/<name>/logs/companion.log` (5 MB x 3), and
  keeps `/files/<name>/status.json` current: `state` (starting, installing, running, not configured, failed,
  stopped), `heartbeat`, `version` (the checkout's commit) and `error`.

`companion.py` is the contract with the hub (database tables, heartbeat, settings, asks). Any bot that writes that
folder shows up on the hub.

### Environment

| Variable | Default | |
|---|---|---|
| `COMPANION_NAME` | `Companion` | The name people tag; used in messages and in the agent's prompts. |
| `COMPANION_ID` | `NAME` lowercased | The companion's id on the hub. |
| `COMPANION_AGENT` | `agent` | The agent it lives in. |
| `COMPANION_BRIDGE` | `http://agent-<agent>:8790` | That agent's Accounts bridge. |
| `COMPANION_ORG` | `the company` | Default for the "Where you work" setting (prompt wording, what counts as "outside"). |
| `COMPANION_DEFAULT_PROJECT` | `/workspace` | Default for the "Default project" setting: T3 project for tasks it can't place in a known project. |
| `COMPANION_MODE` | `tag` | Default mode (`tag`, `team`, `owner` = dry run); the hub setting overrides it live. |
| `COMPANION_GITHUB_USER` | | Default for "Your GitHub username" (the PR list puts yours first). |
| `COMPANION_QA_EVIDENCE` | | Default for "QA screenshots repository" (`owner/repo`). |
| `COMPANION_PUBLISH_CHANNEL` | | Default product-updates channel id. |
| `COMPANION_SECRETS`, `COMPANION_DATA`, `COMPANION_FILES`, `COMPANION_T3` | `/secrets`, `/data`, `/files`, `/t3` | Mount points. |

### Secrets (`<data>/secrets/companions/<name>/`, mounted read-only at `/secrets`)

| File | |
|---|---|
| `owner.txt` | The owner's Slack user id (`U…`). |
| `bot-token.txt` | Bot token (`xoxb-…`). |
| `app-token.txt` | App-level token with `connections:write` (`xapp-…`), for Socket Mode. |
| `user-token.txt` | The owner's user token (`xoxp-…`), read-only scopes. Optional: without it, tags in the owner's own DMs and team mode don't work. |
| `agent-key.txt` | Shared key for the agent's bridge; the same value must be in the agent's `~/.config/agent/bridge-key`. |
| `github-app-id.txt`, `github-app-key.pem` | Optional, for pull request reviews. Read when used, so they can be added later without a restart. |
| `work-tools.md` | Optional. Prompt text describing the owner's work tools for errands (e.g. a read-only mail search CLI, a password vault CLI in the agent). Without it, errands use only the browser's logins. |

The container runs as uid 1000 (the agent's user, so the agent can read what it is handed): `/data`, `/files` and
`/t3` must be writable by 1000 (`/t3` only for SQLite's `-shm` file), and the secrets readable by it.

### Health

The poll loop rewrites `/data/heartbeat.json` every few seconds, so a container healthcheck can be:
`test $(( $(date +%s) - $(stat -c %Y /data/heartbeat.json) )) -lt 90`.

## Setting it up

Usually the agent does this itself: ask it for a companion and its `companion` skill walks you through the one part
only you can do, creating the Slack app. That part is a manifest link: open it, install the app to your workspace, and
hand over three things: the bot token, an app-level token with `connections:write`, and your Slack member id (plus
your user token if the companion should act as you). The agent saves them with `companion secret`; an admin can also
use `agentctl secret set companion/<name>/bot-token.txt` (and `app-token.txt`, `owner.txt`), or the dashboard's
Secrets screen. The key the companion and its agent share is made by `agentctl apply`, along with the companion's
code checkout. Then invite it to the channels it should post in (`/invite @Companion`).

The manifest is [`slack-manifest.yml`](slack-manifest.yml) if you'd rather create the app by hand (rename "Companion"
first).

### Pull request reviews (optional)

Create a GitHub App (Settings → Developer settings → GitHub Apps → New), no webhook, with these repository
permissions:

| Permission | Access | Why |
|---|---|---|
| Contents | Read and write | read the code; write only to the QA screenshots repository |
| Pull requests | Read and write | the review, inline comments, edits, resolving its threads |
| Issues | Read and write | the QA comment and reactions on the PR conversation |
| Checks | Read | CI state in the PR list |
| Metadata | Read | required |

Install it on the repositories (or the whole organization) it may review: the companion lists whatever the App can
see. Save its App id and a private key as `github-app-id.txt` and `github-app-key.pem`.

**QA screenshots.** GitHub doesn't let an App upload images into comments, so screenshots are committed to a separate
private repository (create an empty one, install the App on it, and set "QA screenshots repository" on the hub).
Comments link the images at the exact commit; anything older than 60 days is pruned monthly by rewriting that
repository's history, so it stays small. Without one, the QA report still posts and lists its screenshots as not
attached.

## Changing your companion

This section is for the AI agent whose companion this is. Your checkout is `/workspace/companions/<name>/` (a git
repo; its `template` branch holds the agentlab template it came from). The running companion executes exactly this
checkout, so every change you commit and restart is live.

Template updates are merged in for you: the host adds each new template version to the `template` branch and merges
it into your branch (`chore: merge agentlab template <from>..<to>`) when your tree is clean and nothing conflicts,
restarts the companion and undoes that merge if it then fails to start. If the hub or `agentctl status` says the
update **needs merging**, run `git merge template`, resolve the conflicts keeping your behaviour, test, commit and
restart.

Where things are:

| What | Where |
|---|---|
| Persona, wording of everything it tells you (the agent) | `bot/prompts.py` |
| Its name | `COMPANION_NAME` (set by the cluster config; ask the owner) |
| The company name, the default project | settings `org` and `default_project`: `companion settings <name> '{"org": "..."}'` or the hub |
| Which Slack message goes where (tags, DMs, threads) | `bot/routing.py`, then `bot/requests.py` for the owner's tags on other people's messages |
| A task: Slack thread <-> T3 chat, progress lines, retries | `bot/tasks.py` (T3 access in `bot/t3.py`) |
| What you hand back through files (posts, polls, approvals, logins) | `bot/outbox.py`, `bot/posts.py`, `bot/polls.py`, `bot/errands.py` |
| Buttons | `slack.app.action('<id>')` handlers next to the feature (e.g. the end of `bot/errands.py`) |
| Settings the owner sees on the hub | `SCHEMA` in `bot/config.py`, read with `COMP.setting('<key>')` |
| Pull request review and QA | `bot/reviews.py` (Slack and hub side), `reviewer/` (GitHub side, the review brief in `reviewer/prompt.py`) |
| The poll loop (anything periodic) | `bot/main.py` |

How to add something:

- **A new command or behaviour in Slack**: add a branch in `routing.route` (or a word check in `tasks`), do the work
  in a module of its own, and run slow parts with `jobs.run_later` so Slack's handler returns at once.
- **Something periodic**: a `tick()` in your module, called from `main.poll` inside `_guarded`.
- **A new setting**: add it to `SCHEMA`; the hub shows it, and `COMP.setting` re-reads it live.
- **A dependency**: add it to `requirements.txt`; the next restart installs it.
- **Never** give the agent a way to send to Slack or GitHub directly: it writes files, the companion checks and sends.

Then:

1. Add or change a test in `tests/` (they fake Slack, T3 and GitHub; look at a neighbouring test).
2. `companion test <name>` runs the checkout's tests. Fix until they pass.
3. Commit (`git commit -am "<what and why>"`): the commit is the companion's version, shown in its status.
4. `companion restart <name>` restarts it on your checkout; `companion status <name>` and `companion logs <name>`
   show whether it came up. If it doesn't, read the log, fix, and restart again (`git revert` gets you back).

Settings and secrets (tokens, the GitHub App) are the owner's: they change them on the hub, not you.

`base/run.py` is baked into the image: editing it here changes nothing.

## Development

From the checkout root:

```
pip install -r tests/requirements.txt
python -m pytest -q
docker build -t agentlab/companion .   # the base image (agentlab repo only)
```

Tests replace Slack, T3 and GitHub with recording fakes; nothing leaves the machine.
