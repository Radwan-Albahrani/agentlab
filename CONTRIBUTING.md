# Contributing to agentlab

Thanks for helping. agentlab runs on people's own machines with their code and logins on it, so changes are held to a
simple bar: small, tested, and easy to read.

## Before you start

- **Bugs:** open an issue with what you ran, what you expected, and the output of `agentctl doctor --json` (remove
  anything private first).
- **Features:** open an issue first so we can agree on the shape before you write code. Anything that crosses parts
  (cli, gate, hub, image, companion, host) starts as a change to [docs/architecture.md](docs/architecture.md).
- **Security problems:** never in a public issue. See [SECURITY.md](SECURITY.md).

## Making a change

1. Fork, then branch from `main` (`fix/gate-host-case`, `feat/hub-device-names`).
2. Keep the change focused; one pull request, one purpose.
3. Run the checks. They need only Docker:
   ```sh
   scripts/check.sh            # everything
   scripts/check.sh cli gate   # just the parts you touched
   FIX=1 scripts/check.sh lint # let ruff fix and format
   ```
4. Add or update tests for what you changed. Security-relevant code (gate, hub access, firewall, anything that reads
   files agents control) needs a test for the attack it prevents, not just the happy path.
5. Open a pull request against `main` and fill in the template. CI must pass; a maintainer reviews and merges.

`main` is protected: nobody pushes to it directly, history is never rewritten, and every change lands through a
reviewed pull request with green checks.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/), checked on every pull request:

```
feat(hub): show each paired device's last use
fix(gate): refuse mixed-case hosts that aren't ours
docs(readme): explain the Tailscale-only setup
chore(deps): bump traefik to v3.3.5
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`, `perf`, `build`. Scopes are the folder names (`cli`,
`host`, `image`, `gate`, `hub`, `companion`, `skills`) or `deps`, `readme`. Pull requests are squash-merged, so the
pull request title is the commit message: write it in the same format.

## Dependencies

Dependabot opens grouped weekly updates for Actions, Python, the hub's bun packages and the Docker base images. Its
automatic *security* fix pull requests for the hub fail: they run as npm and can't rewrite `bun.lock`. When an alert
names a hub package, bump it in `hub/web/package.json`, run `bun install` in the hub's pinned Bun image (see
`hub/test.sh`) to update `bun.lock`, and check with `hub/test.sh all`; or wait for the weekly bun update.

## Code style

- Clean, readable, not over-engineered. Comments say *why*, not what; module headers say why the mechanism exists.
- Python: standard library where it's enough; `ruff` with the repo's [`ruff.toml`](ruff.toml) (single quotes, 120
  columns). The CLI stays standard-library only.
- Shell: `set -eu`, passes `shellcheck`.
- Hub web: TypeScript, React, StyleX, Base UI; `bun`; lint, typecheck and format must pass (`hub/test.sh check`).
- LF line endings everywhere (`.gitattributes` enforces it).
- Nothing personal in the repo: no real names, emails, domains, IPs, tokens or company details. Tests and examples use
  `example.com`.

## Licence

By contributing you agree that your contributions are licensed under the [MIT License](LICENSE).
