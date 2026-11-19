# Companion

A Slack bot that is one person's agent in Slack. It lives in that person's agent environment: every task it takes
becomes a T3 chat in their agent, and the chat's progress and answer come back to the Slack thread. Only the owner
gives it work; anyone else who addresses it gets one polite refusal.

What it does:

- **Tasks.** Tag it (`@Companion fix the flaky login test`) or DM it, and it starts a T3 chat with the whole thread
  as context. Reply in the thread to continue. It shows live progress, retries when the model is busy, and splits
  big work into T3 child threads. Replies and files (screenshots, documents) go into that thread. Settings →
  "People who can tag it" lets colleagues give it work too; their sensitive steps wait for your Approve.
- **Side answers.** A status question in a task's thread ("status?", "any update?", "what's going on") or anything
  starting with `btw` is answered on the side: the agent's quick model (Haiku, through the bridge's triage) reads a
  short digest of the chat (its latest steps, workers, PRs) and replies in two sentences at most. The chat is never
  messaged or interrupted.
- **Answered where it was asked.** Every message is answered in the thread it was written in: its side answer, the
  "queued" note, the thinking line and the turn's final message. Each turn records its `place` (`thread` or `case`);
  the one exception is a colleague's turn in a private case, whose final message is yours. The thinking line knows
  where it was posted and is edited there; when a newer message moves the turn, the line moves with it. An edit that
  adds the companion's tag to a message counts as a new message.
- **Where a chat starts.** Every new T3 chat is routed by `bot/projects.py`: only work projects (the codebases) are
  ever chosen, never a companion's own folder (`/workspace/companions/<name>`), so its own name in an ask leads
  nowhere. Each route says why (`named`, `channel`, `thread`, `topic`, `default`; `repo` or `checkout` for reviews),
  and the hub's Cases tab shows it under each case.
- **Cases.** Every conversation someone else has with it (a colleague's DM or tag, the requests channel, an errand,
  a review they asked for once they talk in it) is a case you follow from one thread in your DM: what they wrote and
  everything it sent them land there, full text. The agent talks to the two of you on purpose: they hear only the
  messages it chooses to send them, and its final message every turn is yours (a turn that sent them nothing says so).
  Your own messages in the case thread (or in the T3 chat directly) are private; theirs wait while you talk to it.
  What you write in their thread is public and answered there. Everything
  waiting on you (approvals, posts, replies, logins) has its own card, and a card that is no longer waiting decides
  nothing. The hub's Cases tab shows each case with every message's state, and what waits on you on top.
- **Explicit states.** A task names who it is with (`party`), where you follow it (`case`), the turn under way
  (`turn`) and where it stands (`phase`), all in `bot/machine.py`. Every message in and out, and everything waiting
  on you, is an item in the task's ledger (`bot/ledger.py`) that moves only along its state machine (received →
  waiting for you → approved → sent, or refused, rejected, replaced, withdrawn, failed); a move it does not allow is a
  bug, not a state. The agent hands everything over through one file, `outbox/<task>/send.json`, where each item names
  its `type` and a message its `to`, with no defaults, and reads what became of each one in `receipts.json`.
- **Errands.** Tag it bare on someone else's message and it handles their request as you (find a document, give
  access, look something up). Anything sensitive (access, money, deleting, sharing) waits for your Approve; replies to
  them wait for your Send. Team mode also notices colleagues asking you directly; dry-run mode lets you rehearse.
- **A requests channel.** Pick one on the hub ("Requests channel") and invite the companion. Anyone on the team tags it
  with an ask there (untagged messages are left alone); it comes to your DM with Approve and Decline. Approved, it runs
  for them in its thread (a PR link is a review they follow) and their tagged replies there steer it (one that leaves what you approved, or wants sensitive
  information, comes back to you first); declined, they
  are told. The card is the ask's case: while it waits, your replies under it go to them; once taken on, you are
  talking to the agent about it (see Cases). Anything they add (tagged) while it waits joins the ask.
- **Posts, DMs and polls.** The agent never posts itself: it writes a file and the companion previews it for you,
  then posts it, DMs the people you named, or runs a poll (buttons, live count, closing on time, the winner).
- **Product-update drafts.** Drafts the agent prepares are previewed in your DM; reply to revise, tap to post, and a
  revision of a posted update edits the post in place.
- **Pull request review and QA.** From the hub's Pull requests tab or Slack (`@Companion <PR link>`, or "review"
  under a message linking a PR). A lead T3 chat reviews in lanes and runs the app to QA it, then the companion posts
  one review as its GitHub App: findings on their lines (one-click suggestions when small), a QA comment with
  screenshots, and on a re-review it edits its own comments and resolves the threads that were fixed. Reviews asked
  for while others are still going form a batch with one Slack card (in your DM for the hub, in the asking thread for
  Slack), edited as each PR moves from queued to reviewing to its outcome; each finished PR is a reply in the card's
  thread, and the batch ends with one "All N reviews done" message. A review's questions come in that thread too:
  reply there (start with `#5922` when several reviews ask at once). "Reviews at a time" is a hub setting, and
  "GitHub people" pairs GitHub logins with Slack people, who get a DM with the result of a review of their PR.
  Colleagues can ask too ("Who can ask for reviews": everyone on the team by default): a DM or tag with a PR link
  joins your batch, with "for <name>" on the card (asking for one already going follows it). You get its questions;
  they get a status line in their thread that follows it (queued, reviewing, waiting on you, paused) and the result
  as a reply, three reviews at a time each.

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
update **needs merging**, the host starts a chat asking you to merge it: run `git merge template`, resolve the
conflicts keeping your behaviour and the template's fixes (take the template's version where both fix the same thing),
test, commit and restart. A bug you fix in the template's own code belongs in agentlab too: tell the person.

Where things are:

| What | Where |
|---|---|
| Persona, wording of everything it tells you (the agent) | `bot/prompts.py` |
| Its name | `COMPANION_NAME` (set by the cluster config; ask the owner) |
| The company name, the default project | settings `org` and `default_project`: `companion settings <name> '{"org": "..."}'` or the hub |
| Which Slack message goes where (tags, DMs, threads) | `bot/routing.py`, then `bot/requests.py` for the owner's tags on other people's messages |
| A task: Slack thread <-> T3 chat, progress lines, retries | `bot/tasks.py` (T3 access in `bot/t3.py`) |
| What the agent hands over (send.json: messages, polls, edits, approvals, logins) and its receipts | `bot/outbox.py` (intake), then `bot/posts.py`, `bot/polls.py`, `bot/errands.py`, `bot/cases.py` |
| Every message in and out, and what waits on the owner: items and their state machine | `bot/ledger.py` |
| Who a task is with, its case, its turn and phase | `bot/machine.py` |
| A conversation followed from the owner's DM (cases): the case thread, rendered from the ledger | `bot/cases.py` |
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
