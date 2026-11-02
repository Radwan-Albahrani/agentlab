"""Everything the hub reads and writes on disk, one module per source:

  watch       the host watcher's output (/watch = <data>/hub/watch) and requests to it (rescan, cleanup, restart,
              logs, deploy)
  stacks      the compose files agentctl rendered (/rendered = <data>/rendered, read-only)
  companions  what companion bots publish (/companions/<name>): heartbeat, tasks, events, settings
  secrets     <data>/secrets (/secrets) and what each one is for (secrets-map.json)

Edits keep the previous version in a .versions/ folder next to the file (files.py)."""

from . import companions, secrets, stacks, watch

__all__ = ['companions', 'secrets', 'stacks', 'watch']
