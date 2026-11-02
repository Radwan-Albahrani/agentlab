"""Tuning for the agents' heavy-job throttle: the one place to change headroom, waiting and estimates. The budgets
themselves come from cluster.json: the pool is agentlab.slice (limits.total_memory) and each agent's room is its own
container's mem_limit, both read live from the cgroups. The agents' shim gets MAX_WAIT_S through the spool."""

import cluster

_cfg = cluster.load()
DATA = cluster.data_dir(_cfg)

# Budgets. A job is admitted only if its expected peak fits both its agent and the shared pool.
POOL_HEADROOM_MB = 2048  # admit up to the slice's MemoryHigh, where the kernel starts slowing every agent
AGENT_HEADROOM_MB = 1024  # room for the agent's own T3, chats and MCP servers to grow between checks
SWAP_CAP_MB = 1024  # admit nothing new while more swap than this is in use

# Disk. The disk holds the agents' work and T3's SQLite alike: a congested disk stalls every chat.
IO_PRESSURE_MAX = (_cfg.get('limits') or {}).get('throttle', {}).get('io_psi_max', 25)  # PSI io "some" avg10, %
ADMIT_GAP_S = 10  # space starts so disk pressure (a 10 s average) shows a new job's load before the next

MAX_WAIT_S = 480  # a job waits at most this long, then runs anyway, so agents' tool calls never time out
STALE_S = 45  # a job whose shim stopped reporting this long ago is gone
POLL_S = 0.5

PEAK_HISTORY = 5  # an estimate is the largest of a job's last few measured peaks...
PEAK_MARGIN = 1.15  # ...plus this margin
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

SPOOL = '.local/state/agent-throttle'  # inside each agent's home; the shim sees the same folder as ~/<SPOOL>
STATE_DIR = f'{DATA}/hub/throttle'
POOL_CGROUP = '/sys/fs/cgroup/agentlab.slice'
AGENT_UID = 1000
