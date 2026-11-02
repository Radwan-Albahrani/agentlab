# agentctl

Makes one Linux server match `/etc/agentlab/cluster.toml` (or `--config`, or `$AGENTLAB_CONFIG`). Python 3.12
standard library only; runs straight from the checkout. `cli/agentctl setup` is the usual start: it asks a few
questions (or takes them as flags), writes the config, puts agentctl on PATH with an `agentlab` group whose members run
the read-only commands without sudo, then installs and starts everything. Commands that change the host re-run
themselves through sudo, so nobody types `sudo agentctl` (see `privileges.py`).

```
agentctl setup [--reach me|tailnet|cloudflare|tinyauth] [--admin E] [--domain D] [--people P] [...]
                                        guided: questions, cluster.toml, then init, install, cloudflare, apply
agentctl secret set <name> | list       save a secret from stdin (hidden prompt at a terminal) where agentlab reads it
agentctl init                           PATH link, agentlab group, starter config (never overwrites); setup runs it
agentctl doctor                         every check, each with its fix (root-only ones need sudo)
agentctl install [--only STEP ...]      host setup: host/install/NN-*.sh, then the images
agentctl apply [--dry-run] [--stack S] [--build]
agentctl agent add <id> <email> | remove <id> [--keep-data] [--yes] | list
agentctl companion create <agent> <name> [--display-name X] | remove <agent|-> <name>
agentctl cloudflare setup [--dry-run]
agentctl backup run | list | restore <date> <agent> [--yes]
agentctl images build [NAME ...] | pull [NAME ...]
agentctl status
agentctl config [edit]                  the resolved config; `edit` opens $EDITOR (sudoedit) and validates
```

Built for agents as much as people: only `setup` at a terminal and `secret set` ever ask anything (every setup
answer is also a flag); `--json` prints one JSON object
`{ok, exit, error, result, changes, messages, warnings}`; exit codes are 0 done, 1 failed, 2 needs `--yes` or a
manual step (the error says which). Destructive commands print their plan and stop without `--yes`.
Without a terminal (or with `--json`) elevation uses `sudo -n`; when sudo wants a password the command exits 2
with `result: {needs: "sudo", command}` instead of waiting on a prompt.

| Module | What |
|---|---|
| `config.py` | validation and the resolved config (`cluster.json` is its public part) |
| `render.py` | compose files, the edge's two-pass routing, the firewall rules |
| `apply.py` | folders, storage, networks, rendering, images, deploys, companion seeding |
| `deploy.py` / `coolify.py` | Compose or Coolify deploys, network joins |
| `disks.py` | shared pool / per-person ext4 images (grow-only, never formats a filesystem) |
| `cloudflare.py` | finding the account, zone and team from the token; tunnel, DNS, Access applications, the people policy |
| `setup.py` | the guided setup: answers, the cluster.toml it writes, running the steps and pausing for a person |
| `secret.py` | `secret set`: known secrets and where each lives |
| `companions.py` | companions agents create and remove (`<data>/state/companions.json`) |
| `tomledit.py` | comment-preserving edits to cluster.toml |

Tests: `cd cli && python3 -m unittest discover -s tests`.
