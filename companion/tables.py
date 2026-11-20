"""companion.db as typed SQLAlchemy models: the tables companion.py's docstring describes (the hub reads them)."""

from typing import Any, Literal, TypedDict

from sqlalchemy import JSON, Boolean, Float, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, Any: JSON}  # noqa: RUF012 (SQLAlchemy reads it from the class)


class Event(Base):
    """Something that happened, for the hub's activity: append-only."""

    __tablename__ = 'events'
    __table_args__ = (Index('events_at', 'at'), Index('events_kind', 'kind', 'at'))

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[float] = mapped_column(Float)
    kind: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    task: Mapped[str | None] = mapped_column(Text)
    to: Mapped[str | None] = mapped_column('to', Text)
    detail: Mapped[str | None] = mapped_column(Text)
    ok: Mapped[bool] = mapped_column(Boolean, default=True, server_default='1')


class TaskCard(Base):
    """A task as the hub shows it (bot/publish.py card): upserted, never deleted."""

    __tablename__ = 'tasks'
    __table_args__ = (Index('tasks_started', 'started'),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, default='')
    kind: Mapped[str] = mapped_column(Text, default='')
    requester: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(Text, default='')
    waiting: Mapped[str] = mapped_column(Text, default='')
    outcome: Mapped[str] = mapped_column(Text, default='')
    started: Mapped[str] = mapped_column(Text, default='')
    ended: Mapped[str] = mapped_column(Text, default='')
    thread: Mapped[str] = mapped_column(Text, default='')
    slack: Mapped[str] = mapped_column(Text, default='')
    source: Mapped[str] = mapped_column(Text, default='')
    updated: Mapped[float | None] = mapped_column(Float)
    resumes_at: Mapped[str] = mapped_column(Text, default='')
    started_by: Mapped[str] = mapped_column(Text, default='')
    via: Mapped[str] = mapped_column(Text, default='')
    approved_by: Mapped[str] = mapped_column(Text, default='')
    party: Mapped[str] = mapped_column(Text, default='')
    phase: Mapped[str] = mapped_column(Text, default='')
    case_link: Mapped[str] = mapped_column(Text, default='')
    project: Mapped[str] = mapped_column(Text, default='')
    route_by: Mapped[str] = mapped_column(Text, default='')
    route_why: Mapped[str] = mapped_column(Text, default='')


CARD = tuple(c.key for c in TaskCard.__table__.columns if c.key != 'updated')


class Item(Base):
    """A ledger item (bot/ledger.py): every message in and out of a task and what waits on the owner."""

    __tablename__ = 'items'
    __table_args__ = (Index('items_task', 'task', 'seq'),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    task: Mapped[str] = mapped_column(Text)
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    at: Mapped[float] = mapped_column(Float)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated: Mapped[float | None] = mapped_column(Float)


class Poll(Base):
    """A poll the companion runs (bot/polls.py card)."""

    __tablename__ = 'polls'

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    task: Mapped[str] = mapped_column(Text)
    open: Mapped[bool] = mapped_column(Boolean)
    closes: Mapped[float | None] = mapped_column(Float)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated: Mapped[float | None] = mapped_column(Float)


class Pull(Base):
    """An open pull request the companion can review: the list is replaced on each re-read."""

    __tablename__ = 'pulls'

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    repo: Mapped[str] = mapped_column(Text)
    number: Mapped[int] = mapped_column(Integer)
    updated: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)


class Stored(Base):
    """The bot's own state, one JSON document per key (bot/state.py); the hub ignores it."""

    __tablename__ = 'store'

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    updated: Mapped[float | None] = mapped_column(Float)


# The rows the bot publishes, as dicts: what Companion.tasks/items/polls/pulls take and what the hub reads back.

TaskStatus = Literal['working', 'waiting', 'paused', 'done', 'failed', 'stopped']  # the hub's coarse status


class CardRow(TypedDict):
    """A task as the hub shows it (bot/publish.card); every value is stored as text."""

    id: str
    title: str
    kind: Literal['task', 'errand', 'review']
    requester: str
    status: TaskStatus
    waiting: str
    outcome: str
    started: str
    ended: str
    thread: str
    slack: str
    source: str
    resumes_at: float | str  # epoch while paused with a known reset, else ''
    started_by: str
    via: str
    approved_by: str
    party: str
    phase: str
    case_link: str
    project: str
    route_by: str
    route_why: str


class ItemRow(TypedDict):
    """A ledger item as the hub stores it (bot/ledger.rows): data holds only what may be shown."""

    id: str
    task: str
    seq: int
    kind: str
    state: str
    at: float
    data: dict[str, Any]


class Voter(TypedDict):
    name: str
    avatar: str


class Option(TypedDict):
    label: str
    votes: int
    voters: list[Voter]


class PollRow(TypedDict):
    """A poll as the hub shows it (bot/polls.card)."""

    id: str
    task: str
    open: bool
    closes: float
    closed: float | None
    question: str
    channel: str
    link: str
    multiple: bool
    options: list[Option]


class Label(TypedDict):
    name: str
    color: str


class OpenPull(TypedDict):
    """An open pull request (reviewer/pulls.open_pulls), kept by the bot (State.pulls) and listed by the hub."""

    id: str
    repo: str
    number: int
    title: str
    url: str
    draft: bool
    author: str
    avatar: str
    labels: list[Label]
    additions: int
    deletions: int
    created: str
    updated: str
    head: str
    ci: str


class Counts(TypedDict):
    findings: int
    blocking: int
    open: int
    qa: str


class ShownFinding(TypedDict):
    """A finding as the hub shows it (reviews._detail)."""

    title: str
    severity: str
    lane: str
    path: str
    line: int | None
    start_line: int | None
    body: str
    link: str


class ShownQa(TypedDict):
    verdict: str
    text: str
    url: str


class Detail(TypedDict):
    """The short review the hub shows when a PR is opened (reviews._detail)."""

    findings: list[ShownFinding]
    qa: ShownQa
    review_url: str


class RunPos(TypedDict):
    """Where a PR stands in the current review batch."""

    n: int
    of: int
    done: bool


class PullReview(TypedDict, total=False):
    """A PR's latest review on the hub's list (bot/reviews.rows)."""

    status: str
    outcome: str
    task: str
    head: str
    at: str
    url: str
    counts: Counts
    resumes_at: float | None
    detail: Detail
    run: RunPos


class PullRow(OpenPull):
    review: PullReview | None
