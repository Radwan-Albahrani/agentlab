# hub

The cluster's dashboard at `hub_domain`: a stdlib Python backend (`hub.py`, JSON API in `routes.py`) serving a React
app (`web/`, StyleX + Base UI, built with Bun). Everyone with an agent uses it, scoped to their own agents and those
agents' companions; admins see everything plus the cluster screens (Services, Configs, Secrets, Notifications,
Display). See [docs/architecture.md](../docs/architecture.md) → "Your hub".

## How it decides who you are

The edge's second pass sets `X-Agentlab-User` after the gate checked the sign-in (and strips any client copy first).
`access.py` trusts that header and, with Cloudflare Access, also verifies the `Cf-Access-Jwt-Assertion` token itself
(RS256 against the team's keys, audience, issuer, expiry) and requires it to name the same person. `scope.py` turns
the email into a viewer (admin from `auth.admins`, owned agents by `owner`); every route and screen asks it, so
someone else's agent or companion is never sent and its routes answer 403. With `auth.mode = "none"` the hub only
answers when started with `HUB_ALLOW_NONE=1` (local testing).

## What it reads

| Env | Default | What |
|---|---|---|
| `HUB_CONFIG` | `/etc/agentlab/cluster.json` | the rendered cluster (re-read when it changes) |
| `WATCH_DIR` | `/watch` | the host watcher's folder (`<data>/hub/watch`): usage, containers, events, `requests/` |
| `RENDERED_DIR` | `/rendered` | `<data>/rendered` (read-only): the compose files the Configs screen shows |
| `COMPANIONS_DIR` | `/companions` | `<data>/companions`: what each companion publishes |
| `SECRETS_DIR` | `/secrets` | `<data>/secrets`; a companion's own in `companions/<name>/` (`secrets-map.json` says what each is) |
| `AGENTS_DIR` | `/agents` | `<data>/agents`: companion logs and status in each workspace, T3 databases for pushes |
| `NOTIFY_DATA` | `/data` | the hub's own state (display settings, push settings) |
| `BARK_URL`, `BARK_PUBLIC` | empty | optional phone pushes through a Bark server; off when empty |
| `HUB_AGENT_URL` | empty | tests only: a `{id}` URL template instead of each agent's `upstream` + `:8790` |

## Develop and test

Everything runs in pinned containers; only Docker is needed.

```
hub/test.sh check            backend ruff + unit tests; web types, lint, format, unit tests, build (FIX=1 autofixes)
hub/test.sh build [tag]      check, then build agentlab/hub:<tag> (default: test)
hub/test.sh instance start   a throwaway hub on 127.0.0.1:7189 over example data (tests/fixtures.py) and fake agents
hub/test.sh e2e [url] [args] Playwright click-through (SHOTS=<dir> saves screenshots; extra args go to playwright)
hub/test.sh all              build, start the throwaway hub, e2e, stop it
```

The web app has two TypeScripts on purpose: `typescript7` (the native compiler) type-checks, while `typescript` stays
on 6.0 because typescript-eslint's typed rules don't support 7 yet. Drop the alias once they do.

For the web app alone: `hub/test.sh instance start`, then `cd web && bun install && bun run dev` (it proxies `/api` to
the throwaway hub, or to `HUB_URL`).
