"""Environment, secrets and paths (read once at start) and the hub-editable settings (re-read on every use)."""

import os
import time

from companion import Companion

SECRETS = os.environ.get('COMPANION_SECRETS', '/secrets')


def secret(name):
    with open(os.path.join(SECRETS, name)) as f:
        return f.read().strip()


def optional_secret(name):
    """The secret, or '' when the file is missing."""
    try:
        return secret(name)
    except OSError:
        return ''


NAME = os.environ.get('COMPANION_NAME', 'Companion')
ID = os.environ.get('COMPANION_ID', NAME.lower())
OWNER = secret('owner.txt')  # Slack user id of the only person it works for
AGENT = os.environ.get('COMPANION_AGENT', 'agent')
BRIDGE = os.environ.get('COMPANION_BRIDGE', f'http://agent-{AGENT}:8790')  # the agent's Accounts bridge
T3 = os.environ.get('COMPANION_T3', '/t3')  # the agent's ~/.t3/userdata (read-only)
# Same folder twice: FILES as mounted here, AGENT_FILES as the agent sees it.
FILES = os.path.join(os.environ.get('COMPANION_FILES', '/files'), ID)
AGENT_FILES = f'/workspace/.companion/{ID}'
DATA = os.environ.get('COMPANION_DATA', '/data')

# Seconds.
POLL = 3
ASKS_POLL = 0.5
SETTLE = 60  # an orchestrator's wait for more workers before its turn counts as finished
STATUS_EVERY = 8  # minimum between live edits of a "thinking" line
REQ_SETTLE = 20  # wait for a burst of messages to the owner to finish
RECENT = 15 * 60  # a new (non-thread) message's context: the messages this long before it

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
        'key': 'access',
        'label': 'People who can tag it',
        'type': 'people',
        'when': {'mode': ['tag', 'team']},
        'default': [],
        'help': f'Besides you, these people can tag or DM @{NAME} with work. It works for them with your tools; '
        'anything sensitive (access, money, deleting, live data, sharing, posting elsewhere) waits for your '
        'approval in your DM.',
    },
    {
        'key': 'auto_retry',
        'label': 'Retry when the model is busy',
        'type': 'bool',
        'default': True,
        'help': 'When a run fails on capacity, rate limits or a server error, say "continue" after 30 s, 90 s and 3 min.',
    },
    {
        'key': 'org',
        'label': 'Where you work',
        'type': 'text',
        'default': os.environ.get('COMPANION_ORG', 'the company'),
        'help': "Used in the agent's prompts: what counts as going outside, who colleagues are.",
    },
    {
        'key': 'default_project',
        'label': 'Default project',
        'type': 'text',
        'default': os.environ.get('COMPANION_DEFAULT_PROJECT', '/workspace'),
        'help': "The T3 project (a folder in the agent's /workspace) for tasks that name no known project.",
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


def has_access(user):
    """The owner, or someone they gave access to (not in dry run)."""
    return user == OWNER or (mode() != 'owner' and user in (COMP.setting('access') or []))


def auto_retry():
    return COMP.setting('auto_retry')


def org():
    return (COMP.setting('org') or '').strip() or 'the company'


def default_project():
    return (COMP.setting('default_project') or '').strip() or '/workspace'


def publish_channel():
    return (COMP.setting('publish_channel') or '').strip()


def evidence_repo():
    return (COMP.setting('qa_evidence_repo') or '').strip()


def work_tools():
    """Prompt text describing the owner's work tools, from the optional secret work-tools.md."""
    return optional_secret('work-tools.md')


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)
