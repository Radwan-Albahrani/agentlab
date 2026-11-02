"""Fixed configuration (environment, secrets, paths) and the live settings the hub can change.

Environment and secrets are read once at start. Settings (mode, auto-retry, publish channel) live in the
companion folder and are re-read on every use, so a change on the hub takes effect within seconds."""

import os
import time

from companion import Companion

SECRETS = os.environ.get('COMPANION_SECRETS', '/secrets')


def secret(name):
    with open(os.path.join(SECRETS, name)) as f:
        return f.read().strip()


def optional_secret(name):
    """'' when the file is missing or still empty (the GitHub App is set up later, on the hub's Secrets page)."""
    try:
        return secret(name)
    except OSError:
        return ''


NAME = os.environ.get('COMPANION_NAME', 'Companion')  # how it calls itself in Slack and in the agent's prompts
ID = os.environ.get('COMPANION_ID', NAME.lower())  # its folder names and its id on the hub
ORG = os.environ.get('COMPANION_ORG', 'the company')  # where the owner works, for the agent's prompts
OWNER = secret('owner.txt')  # the Slack user id of the only person it works for
AGENT = os.environ.get('COMPANION_AGENT', 'agent')  # the agent whose environment it lives in
BRIDGE = os.environ.get('COMPANION_BRIDGE', f'http://agent-{AGENT}:8790')  # that agent's Accounts bridge
T3 = os.environ.get('COMPANION_T3', '/t3')  # the agent's ~/.t3/userdata (read-only)
# The agent's /workspace/.companion is mounted at /files; each companion keeps to its own folder in it (attachments,
# outboxes, drafts, logs, status.json), so two companions of one agent never see each other's work.
FILES = os.path.join(os.environ.get('COMPANION_FILES', '/files'), ID)
AGENT_FILES = f'/workspace/.companion/{ID}'
DATA = os.environ.get('COMPANION_DATA', '/data')  # <data>/companions/<name>/: its database + what the hub reads
DEFAULT_PROJECT = os.environ.get('COMPANION_DEFAULT_PROJECT', '/workspace')

POLL = 3  # s between checks of every task
SETTLE = 60  # s an orchestrator gets to start more workers before its turn counts as finished
STATUS_EVERY = 8  # s minimum between live edits of a "thinking" line
REQ_SETTLE = 20  # s a burst of messages to the owner may keep arriving before it is looked at

MODES = [
    {
        'value': 'tag',
        'label': 'Restricted',
        'help': f"Acts only when you tag @{NAME}. A bare tag on someone's message runs it as an errand for them.",
    },
    {
        'value': 'team',
        'label': 'Team',
        'help': 'Also notices when a colleague tags or DMs you: clear small errands start on their own (replies still '
        'wait for your Send), bigger asks get a heads-up in your DM, the rest is ignored.',
    },
    {
        'value': 'owner',
        'label': 'Dry run',
        'help': 'Practice: messages you send yourself play the colleague, and nothing is ever sent to anyone else.',
    },
]
SCHEMA = [
    {
        'key': 'mode',
        'label': 'Mode',
        'type': 'choice',
        'options': MODES,
        'help': f'When {NAME} takes work on its own.',
        'default': os.environ.get('COMPANION_MODE', 'tag'),
    },
    {
        'key': 'auto_retry',
        'label': 'Retry when the model is busy',
        'type': 'bool',
        'default': True,
        'help': 'When a run fails on capacity, rate limits or a server error, say "continue" after 30 s, 90 s and 3 min.',
    },
    {
        'key': 'github_user',
        'label': 'Your GitHub username',
        'type': 'text',
        'default': os.environ.get('COMPANION_GITHUB_USER', ''),
        'help': 'Pull requests you opened are listed first, under "Authored".',
    },
    {
        'key': 'qa_evidence_repo',
        'label': 'QA screenshots repository',
        'type': 'text',
        'default': os.environ.get('COMPANION_QA_EVIDENCE', ''),
        'help': 'A private owner/repo the GitHub App is installed on. QA screenshots are kept there, never in the '
        'reviewed repository, and anything older than 60 days is pruned monthly. Empty: QA reports list their '
        'screenshots as not attached.',
    },
    {
        'key': 'publish_channel',
        'label': 'Product updates channel',
        'type': 'text',
        'default': os.environ.get('COMPANION_PUBLISH_CHANNEL', ''),
        'help': 'Slack channel id that approved product-update drafts are posted to.',
    },
]

COMP = Companion(ID, AGENT, DATA, SCHEMA)


def mode():
    return COMP.setting('mode')


def auto_retry():
    return COMP.setting('auto_retry')


def publish_channel():
    return (COMP.setting('publish_channel') or '').strip()


def evidence_repo():
    return (COMP.setting('qa_evidence_repo') or '').strip()


def work_tools():
    """What the owner's work accounts offer the agent for errands (mail search, a password vault, ...), as prompt
    text from the optional secret work-tools.md; '' when there is none."""
    return optional_secret('work-tools.md')


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)
