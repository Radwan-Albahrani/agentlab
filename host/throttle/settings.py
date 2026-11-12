"""Tuning for the heavy-job throttle; memory budgets are read live from the cgroups."""

import cluster

_cfg = cluster.load()
DATA = cluster.data_dir(_cfg)

POOL_HEADROOM_MB = 2048  # keeps admissions below the slice's MemoryHigh
AGENT_HEADROOM_MB = 1024  # room for the agent's own T3, chats and MCP servers
MEMORY_PRESSURE_MAX = 10  # PSI memory "some" avg10, %; swap in use alone isn't pressure (pages stay swapped out)

IO_PRESSURE_MAX = (_cfg.get('limits') or {}).get('throttle', {}).get('io_psi_max', 25)  # PSI io "some" avg10, %
ADMIT_GAP_S = 10  # PSI avg10 needs this long to show a new job's load

MAX_WAIT_S = 480  # then the job runs anyway, so agents' tool calls never time out
STALE_S = 45  # a job whose shim stopped reporting this long ago is gone
POLL_S = 0.5

PEAK_HISTORY = 5
PEAK_MARGIN = 1.15
DEFAULT_MB = {  # first-run estimates, by tool
    'npm': 1500,
    'pnpm': 1500,
    'yarn': 1500,
    'bun': 1500,
    'npx': 1500,
    'bunx': 1500,
    'pnpx': 1500,
    'tsc': 1500,
    'vitest': 2000,
    'jest': 2000,
    'mocha': 1000,
    'playwright': 2500,
    'next': 2500,
    'vite': 1500,
    'turbo': 2500,
    'nx': 2500,
    'webpack': 2000,
    'cargo': 3000,
    'go': 1500,
    'make': 1500,
    'gradle': 3000,
    'mvn': 2500,
    'pip': 800,
    'pip3': 800,
    'pytest': 1500,
    'docker': 2500,
    'emulator': 3000,
}
DEFAULT_OTHER_MB = 1500

SPOOL = '.local/state/agent-throttle'  # relative to each agent's home; the shim uses the same path
STATE_DIR = f'{DATA}/hub/throttle'
POOL_CGROUP = '/sys/fs/cgroup/agentlab.slice'
AGENT_UID = 1000
