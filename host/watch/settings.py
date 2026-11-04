import os

import cluster

DATA = cluster.data_dir()
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WATCH_DIR = f'{DATA}/hub/watch'  # the hub mounts this at /watch
SECRETS_DIR = f'{DATA}/secrets'
SECRETS_MAP = f'{REPO}/hub/secrets-map.json'
RENDERED_DIR = f'{DATA}/rendered'
COMPOSE_DIR = f'{DATA}/rendered/compose'
AGENTCTL = f'{REPO}/cli/agentctl'

ALERT_LEVELS = (80, 90, 95)  # % full
REARM_BELOW = 5  # points below a level before it alerts again
SCAN_EVERY_S = 3 * 3600  # per-folder du breakdown
SCAN_MIN_BYTES = 200_000_000  # smaller folders are left out of the breakdown

CHECK_EVERY_S = 30
REQUEST_POLL_S = 1
EVENTS_KEPT = 1000
LOG_TAIL_LINES = 400
AGENT_UID = 1000
