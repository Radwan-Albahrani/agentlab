"""The shapes of everything the companion keeps (state.py saves them as JSON): one TypedDict per record.

The states inside them are named by their machines: machine.py (party, case, turn, phase), ledger.py (item states)
and fsm.py (drafts, asks, polls, review entries, retries)."""

from typing import Any, Literal, NotRequired, TypedDict

PartyKind = Literal['owner', 'colleague', 'errand']
Head = Literal['own', 'card', 'errand']
Mode = Literal['private', 'shared']
Place = Literal['thread', 'case']
TurnBy = Literal['owner', 'colleague', 'decision', 't3', 'system']
Outcome = Literal['answered', 'asked', 'silent', 'nothing_to_do', 'failed', 'stopped']
Phase = Literal[
    'working', 'waiting_owner', 'waiting_answer', 'paused', 'answered', 'nothing_to_do', 'stopped', 'failed'
]
RouteBy = Literal['repo', 'named', 'channel', 'thread', 'topic', 'default', 'checkout', 'earlier']


class Party(TypedDict):
    kind: PartyKind
    user: str


class Case(TypedDict):
    ch: str
    ts: str
    head: Head
    mode: Mode
    md: NotRequired[str]
    own: NotRequired[bool]  # saved by older versions (machine.migrate)


class Turn(TypedDict, total=False):  # partial: before the first turn ({}), and as saved by older versions
    n: int
    by: TurnBy
    place: Place
    state: Literal['running', 'ended']
    outcome: Outcome | Literal['']  # '' while running
    at: float
    ended: float


class Line(TypedDict):
    """A thinking line: where it was posted (it is always edited there)."""

    ch: str
    ts: str
    since: float


class Route(TypedDict):
    """Where a task's chat started and why (projects.route)."""

    project: str
    by: RouteBy
    why: str


# Who started a task and how (tasks.audit); "for": who a run from the hub was for.
Audit = TypedDict('Audit', {'by': str, 'via': str, 'approved_by': str | None, 'for': str | None, 'at': float})


class Pause(TypedDict):
    at: float
    resumes_at: float | None
    run: str | None
    nudged: float


class Retry(TypedDict):
    state: Literal['idle', 'waiting', 'sent']
    count: int
    at: float


class Queued(TypedDict):
    """A message that waited for the turn under way (cases.queue)."""

    by: str
    text: str
    files: Any
    ts: str


class ItemData(TypedDict, total=False):
    """What a ledger item says, besides its state (ledger.move takes these)."""

    by: str
    to: str
    label: str
    text: str
    files: list[str]
    private: bool
    first: bool
    ts: str
    card: dict[str, Any]
    ref: str
    side: bool
    held: str | None  # what the gate held back (ledger.move stores None as given)
    after: str
    action: str
    md: str
    post: dict[str, Any]
    paths: list[str]
    where: str
    msgs: list[Any] | None  # [[channel, ts]] of the posted messages
    reply: str
    details: str
    question: bool | None  # None: not asked (ledger.add drops it)
    poll: Any  # the agent's own JSON (outbox.py)
    raw_to: Any
    change: dict[str, Any]


class ItemFields(ItemData, total=False):
    """What ledger.add takes."""

    note: str


class Item(ItemFields, total=False):
    """A ledger item (ledger.py docstring)."""

    id: str
    kind: str
    state: str
    at: float
    updated: float
    history: list[list[Any]]


class Review(TypedDict, total=False):
    """The pull request a review task runs (reviews.start), and what it published."""

    id: str
    repo: str
    number: int
    url: str
    head: str
    installation: int
    rereview: str
    author: str
    title: str
    asked_by: list[str]
    published: str
    summary: str
    counts: dict[str, Any]
    detail: dict[str, Any]


class Task(TypedDict, total=False):
    """One task: a T3 chat followed from a Slack thread (state.new_task)."""

    thread: str
    title: str
    route: Route
    channel: str
    thread_ts: str
    outbox: str
    trigger_ts: str
    line: Line | None
    start: str
    burst_start: str
    seen: str
    step_from: str
    asked: list[str]
    prs: list[str]
    workers_said: int
    last_status: str
    last_status_at: float
    quiet_since: float
    options: dict[str, str]
    key: str
    audit: Audit
    party: Party
    case: Case
    turn: Turn
    phase: Phase
    phases: list[list[Any]]
    items: list[Item]
    items_rev: int
    question: bool
    paused: Pause
    retry: Retry
    review: Review | bool
    seen_ts: str
    latest: str
    ended: str
    closed: str
    poll: str
    queue: list[Queued]
    down_since: float
    nudged: int
    source: str
    source_ch: str
    source_im: bool
    source_thread: str | None
    colleague: str  # also machine.OLD: kept for older readers, removed by migrate
    # saved by older versions; state.prepare_for_start and machine.migrate convert and remove them
    project: str
    retries: int
    retry_at: float
    retry_sent: float
    status_ts: str
    line_start: float
    guest: str
    requester: str
    approved: str | bool
    approval: dict[str, Any]
    post_draft: dict[str, Any]
    reply_draft: dict[str, Any]
    reply_pending: str
    cred_ask: dict[str, Any]
    told: Any
    posted: Any
    answer_to: Any
    active: bool
    outcome: str
    sent: list[dict[str, Any]]
    limit_checked: Any


class Poll(TypedDict, total=False):
    id: str
    channel: str
    text: str
    question: str
    options: list[str]
    closes: float
    multiple: bool
    votes: dict[str, list[int]]
    state: Literal['open', 'closed']
    task: str
    ts: str
    closed: float
    added_by: dict[str, str]
    open: bool  # saved by older versions (state.prepare_for_start)


class Draft(TypedDict, total=False):
    status: Literal['pending', 'posted', 'revising', 'editing', 'discarded']
    revision: int
    dm: str
    thread: str | None
    buttons: str | None
    mtime: float
    posted: dict[str, Any]
    revising: bool  # saved by older versions (state.prepare_for_start)


class Ask(TypedDict, total=False):
    """An ask in the requests channel waiting on the owner (inbox.py)."""

    ch: str
    ts: str
    user: str
    name: str
    text: str
    card: str
    status: Literal['pending', 'approved', 'declined']
    ack: str | None


# A pull request in the review batch (reviews.py, fsm.REVIEW); "for": the colleagues following it.
ReviewEntry = TypedDict(
    'ReviewEntry',
    {
        'id': str,
        'url': str,
        'title': str,
        'state': Literal[
            'queued', 'reviewing', 'waiting', 'paused', 'asked', 'approved', 'changes', 'failed', 'stopped'
        ],
        'asked': dict[str, str],
        'for': list[dict[str, Any]],
        'task': str,
        'rereview': str,
        'began': float,
        'detail': str,
        'link': str,
        'ended': float,
        'paused': float,
        'counts': dict[str, Any],
        'verdict': str,  # older saved entries only: read once into `state` (reviews._upgrade)
        'waiting': bool,  # older saved entries only
    },
    total=False,
)


class Request(TypedDict):
    """Someone asking the owner, collected from Slack (requests.notice, requests.owner_tagged)."""

    ch: str
    ts: str
    thread_ts: str | None
    user: str
    im: bool
    texts: list[str]
    files: list[dict[str, Any]]
    tagged: NotRequired[bool]
    last: NotRequired[float]  # when its latest message came (requests.pending_tick)


class ReviewBatch(TypedDict, total=False):
    """The current review batch (reviews._batch): its card, where it is posted (thread None: top level), its PRs."""

    channel: str
    thread: str | None
    card: str | None
    prs: list[ReviewEntry]
    moved: list[Any]  # old per-PR cards to retire: [channel, card, id, url]
    limit_told: bool


class ReviewQueued(TypedDict):
    """A requested review waiting for a slot (reviews.queue); origin: who asked and where, None from the hub."""

    id: str
    repo: str
    number: int
    origin: dict[str, Any] | None


class Invite(TypedDict):
    """A tag in a channel the companion is not in yet (requests.await_invite)."""

    ch: str
    thread_ts: str | None
    ts: str
    text: str
    at: float


class Listing(TypedDict, total=False):
    """A list read from GitHub hourly (reviews._refresh_people): people [{login, avatar}] or repo names."""

    at: float
    list: list[Any]


class State(TypedDict, total=False):
    """Everything state.py keeps: tasks by key (state.key_of), the rest one record per key."""

    tasks: dict[str, Task]
    polls: dict[str, Poll]
    drafts: dict[str, Draft]
    refused: list[str]
    inbox: dict[str, Ask]
    review_queue: list[ReviewQueued]
    review_batch: ReviewBatch
    review_run: list[dict[str, Any]]  # saved by older versions: reviews._batch migrates it
    pulls: list[dict[str, Any]]
    github_people: Listing
    github_repos: Listing
    authors_told: dict[str, str]
    awaiting_invite: dict[str, Invite]
    evidence_pruned: float
    _invite_check: float
    _drafts_retry: float
