"""The shapes of everything the companion keeps (state.py saves them as JSON): one TypedDict per record.

state.py validates what it loads against State, so a record that doesn't fit (an unknown key, a state no machine
names) stops the companion at start instead of misbehaving later. The states inside the records are named by their
machines: machine.py (party, case, turn, phase), ledger.py (items) and fsm.py (drafts, asks, polls, reviews,
retries)."""

from typing import Any, Literal, NotRequired, TypedDict

from pydantic import ConfigDict, with_config
from reviewer.github import User
from tables import Counts, Detail, Label, OpenPull, ShownFinding, ShownQa

Json = dict[str, Any]  # JSON from outside (Slack, GitHub, the agent's own files): no fixed shape
STRICT = ConfigDict(extra='forbid')  # a key no shape names is a bug
for _shape in (User, Label, OpenPull, Counts, Detail, ShownFinding, ShownQa):  # kept in State, defined where made
    with_config(STRICT)(_shape)

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
# the states of the fsm.py machines
DraftState = Literal['pending', 'posted', 'revising', 'editing', 'discarded']
AskState = Literal['pending', 'approved', 'declined']
PollState = Literal['open', 'closed']
RetryState = Literal['idle', 'waiting', 'sent']
ReviewState = Literal['queued', 'reviewing', 'waiting', 'paused', 'asked', 'approved', 'changes', 'failed', 'stopped']
ItemKind = Literal['in', 'final', 'message', 'edit', 'approval', 'credential', 'poll_change']
ItemState = Literal[
    'received', 'awaiting_owner', 'approved', 'sent', 'silent', 'applied', 'refused', 'rejected', 'replaced', 'withdrawn',
    'failed', 'dry_run', 'lost',
]  # fmt: skip  # ledger.py: STATES per kind, MOVES between them


@with_config(STRICT)
class Party(TypedDict):
    kind: PartyKind
    user: str


@with_config(STRICT)
class Case(TypedDict):
    ch: str
    ts: str
    head: Head
    mode: Mode
    md: NotRequired[str]


@with_config(STRICT)
class Turn(TypedDict, total=False):  # {} before the first turn
    n: int
    by: TurnBy
    place: Place
    state: Literal['running', 'ended']
    outcome: Outcome | Literal['']  # '' while running
    at: float
    ended: float


@with_config(STRICT)
class Line(TypedDict):
    """A thinking line: where it was posted (it is always edited there)."""

    ch: str
    ts: str
    since: float


@with_config(STRICT)
class Route(TypedDict):
    """Where a task's chat started and why (projects.route)."""

    project: str
    by: RouteBy
    why: str


# Who started a task and how (tasks.audit); "for": who a run from the hub was for.
Audit = TypedDict('Audit', {'by': str, 'via': str, 'approved_by': str | None, 'for': str | None, 'at': float})
with_config(STRICT)(Audit)


@with_config(STRICT)
class Pause(TypedDict):
    at: float
    resumes_at: float | None
    run: str | None
    nudged: float


@with_config(STRICT)
class Retry(TypedDict):
    state: RetryState
    count: int
    at: float


@with_config(STRICT)
class Queued(TypedDict):
    """A message that waited for the turn under way (cases.queue)."""

    by: str
    text: str
    files: list[Json] | None
    ts: str


@with_config(STRICT)
class Card(TypedDict):
    """The Slack message where the owner decides on an item."""

    ch: str
    ts: str


@with_config(STRICT)
class PollSpec(TypedDict):
    """A poll as a post asks for it, checked (posts._poll)."""

    question: str
    options: list[str]
    closes: float
    multiple: bool


@with_config(STRICT)
class Post(TypedDict, total=False):
    """A message, poll or edit the agent wants out, checked (posts.py): a channel, people, or an earlier message."""

    channel: str
    to: list[str]
    thread: str
    text: str
    poll: PollSpec
    edit: str  # the ledger id of the message it edits
    where: str
    msgs: list[tuple[str, str]]  # (channel, ts) of the messages it edits


@with_config(STRICT)
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
    card: Card
    ref: str
    side: bool
    held: str | None  # what the gate held back
    after: Literal['turn']  # sent once the turn ends (errands.after_turn)
    action: str
    md: str
    post: Post
    paths: list[str]
    where: str
    msgs: list[tuple[str, str]] | None  # (channel, ts) of the posted messages
    reply: str
    details: str
    question: bool  # the final message asks the owner something
    poll: Json  # the agent's poll, as it wrote it (outbox.py)
    raw_to: Json | list[str] | str  # the agent's "to", as it wrote it
    change: Json  # the agent's poll change, as it wrote it


class ItemFields(ItemData, total=False):
    """What ledger.add takes."""

    note: str


@with_config(STRICT)
class Item(ItemFields, total=False):
    """A ledger item (ledger.py docstring)."""

    id: str
    kind: ItemKind
    state: ItemState
    at: float
    updated: float
    history: list[tuple[ItemState, float, str]]


@with_config(STRICT)
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
    counts: Counts
    detail: Detail


@with_config(STRICT)
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
    phases: list[tuple[Phase, float]]
    items: list[Item]
    items_rev: int
    question: bool
    paused: Pause
    retry: Retry
    review: Review  # a PR review task
    preview: bool  # a hub ask: show its posts to the owner before they go out
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


@with_config(STRICT)
class Poll(TypedDict, total=False):
    id: str
    channel: str
    text: str
    question: str
    options: list[str]
    closes: float
    multiple: bool
    votes: dict[str, list[int]]
    state: PollState
    task: str
    ts: str
    closed: float
    added_by: dict[str, str]


@with_config(STRICT)
class Posted(TypedDict):
    """Where a product update went: its channel and message (None until found), and whether it carries files."""

    channel: str
    ts: str | None
    files: NotRequired[bool]


@with_config(STRICT)
class Draft(TypedDict, total=False):
    status: DraftState
    revision: int
    dm: str
    thread: str | None
    buttons: str | None
    mtime: float
    posted: Posted


@with_config(STRICT)
class Ask(TypedDict, total=False):
    """An ask in the requests channel waiting on the owner (inbox.py)."""

    ch: str
    ts: str
    user: str
    name: str
    text: str
    card: str
    status: AskState
    ack: str | None


@with_config(STRICT)
class Spot(TypedDict):
    """A Slack message: its channel and ts."""

    channel: str
    ts: str


@with_config(STRICT)
class Asker(TypedDict):
    """A colleague following a review (reviews._follow): their thread, the status message kept up to date there."""

    channel: str
    thread: str
    user: str
    name: str
    ts: str
    msg: str | None
    md: str
    shown: str
    told: NotRequired[ReviewState]


# A pull request in the review batch (reviews.py, fsm.REVIEW); "for": the colleagues following it.
ReviewEntry = TypedDict(
    'ReviewEntry',
    {
        'id': str,
        'url': str,
        'title': str,
        'state': ReviewState,
        'asked': Spot,
        'for': list[Asker],
        'task': str,
        'rereview': str,
        'began': float,
        'detail': str,
        'link': str,
        'ended': float,
        'paused': float,
        'counts': Counts,
    },
    total=False,
)
with_config(STRICT)(ReviewEntry)


@with_config(STRICT)
class Request(TypedDict):
    """Someone asking the owner, collected from Slack (requests.notice, requests.owner_tagged)."""

    ch: str
    ts: str
    thread_ts: str | None
    user: str
    im: bool
    texts: list[str]
    files: list[Json]
    tagged: NotRequired[bool]
    last: NotRequired[float]  # when its latest message came (requests.pending_tick)


@with_config(STRICT)
class ReviewBatch(TypedDict, total=False):
    """The current review batch (reviews._batch): its card, where it is posted (thread None: top level), its PRs."""

    channel: str
    thread: str | None
    card: str | None
    prs: list[ReviewEntry]
    limit_told: bool


@with_config(STRICT)
class Origin(TypedDict):
    """Where a review was asked for in Slack, and by whom (by: a colleague; none: the owner)."""

    channel: str
    thread_ts: str
    trigger_ts: str
    via: str
    by: NotRequired[str]
    approved_by: NotRequired[str]


@with_config(STRICT)
class ReviewQueued(TypedDict):
    """A requested review waiting for a slot (reviews.queue); origin None: from the hub."""

    id: str
    repo: str
    number: int
    origin: Origin | None


@with_config(STRICT)
class People(TypedDict):
    """Who can work on the reviewed repos, read from GitHub hourly (reviews._refresh_people)."""

    at: float
    list: list[User]


@with_config(STRICT)
class Repos(TypedDict):
    at: float
    list: list[str]


@with_config(STRICT)
class Invite(TypedDict):
    """A tag in a channel the companion is not in yet (requests.await_invite)."""

    ch: str
    thread_ts: str | None
    ts: str
    text: str
    at: float


@with_config(STRICT)
class State(TypedDict, total=False):
    """Everything state.py keeps: tasks by key (state.key_of), the rest one record per key."""

    tasks: dict[str, Task]
    polls: dict[str, Poll]
    drafts: dict[str, Draft]
    refused: list[str]
    inbox: dict[str, Ask]
    review_queue: list[ReviewQueued]
    review_batch: ReviewBatch | None
    pulls: list[OpenPull]
    github_people: People
    github_repos: Repos
    authors_told: dict[str, str]
    awaiting_invite: dict[str, Invite]
    evidence_pruned: float
    _invite_check: float
    _drafts_retry: float
