"""T3's database (statev2.sqlite) as typed SQLAlchemy models, read-only: the tables and columns agentlab reads.

T3 owns the schema; these mirror it, primary keys as T3 declares them. This file is the source: exact copies live
where other images need it (companion/t3schema.py, hub/notify/t3schema.py), and scripts/check.sh fails if one drifts.
"""

from typing import Any

from sqlalchemy import JSON, ColumnElement, Engine, Integer, Text, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool

# A run in one of these is over; any other status with no end time is in progress.
SETTLED = ('completed', 'cancelled', 'failed', 'interrupted', 'rolled_back')


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = 'projection_projects'

    project_id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str | None] = mapped_column(Text)
    workspace_root: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[str | None] = mapped_column(Text)


class Thread(Base):
    """A chat. payload: lineage.parentThreadId (a worker's lead), pullRequests, branchPullRequest, worktreePath,
    creationSource, createdBy, settledAt, unsettledAt, archivedAt, deletedAt, updatedAt."""

    __tablename__ = 'orchestration_v2_projection_threads'

    thread_id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column('payload_json', JSON)


class Run(Base):
    """One run of a chat: status running | completed | interrupted | cancelled ...; completed_at null while open."""

    __tablename__ = 'orchestration_v2_projection_runs'

    run_id: Mapped[str] = mapped_column(Text, primary_key=True)
    thread_id: Mapped[str] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[str | None] = mapped_column(Text)


class Message(Base):
    """A message in a chat; payload.text is what was said."""

    __tablename__ = 'orchestration_v2_projection_messages'

    message_id: Mapped[str] = mapped_column(Text, primary_key=True)
    thread_id: Mapped[str] = mapped_column(Text)
    run_id: Mapped[str | None] = mapped_column(Text)  # the run that wrote it
    role: Mapped[str | None] = mapped_column(Text)
    streaming: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column('payload_json', JSON)


class Request(Base):
    """A question or approval the chat waits on; payload.responseCapability.type 'message': answered by any message."""

    __tablename__ = 'orchestration_v2_projection_runtime_requests'

    runtime_request_id: Mapped[str] = mapped_column(Text, primary_key=True)
    thread_id: Mapped[str] = mapped_column(Text)
    kind: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column('payload_json', JSON)


class TurnItem(Base):
    """A step of a run: reasoning, assistant_message, command_execution, dynamic_tool, error, *request* ..."""

    __tablename__ = 'orchestration_v2_projection_turn_items'

    turn_item_id: Mapped[str] = mapped_column(Text, primary_key=True)
    thread_id: Mapped[str] = mapped_column(Text)
    ordinal: Mapped[int | None] = mapped_column(Integer)
    type: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column('payload_json', JSON)


def text_of(payload: Any) -> ColumnElement[str | None]:
    """payload.text, in SQL (NULL when the payload has none)."""
    return payload['text'].as_string()


def answered_by_message() -> ColumnElement[bool]:
    """A request the agent ends its turn with, answered by a plain message: T3 doesn't wait on it (non-blocking)
    and cancels it once the next message arrives."""
    return func.coalesce(Request.payload[('responseCapability', 'type')].as_string() == 'message', False)


def parent_of(thread: type[Thread]) -> ColumnElement[str]:
    """The lead chat of a worker chat (newer T3: lineage.parentThreadId; older: parentThreadId)."""
    return func.coalesce(
        thread.payload[('lineage', 'parentThreadId')].as_string(), thread.payload['parentThreadId'].as_string()
    )


def in_progress() -> ColumnElement[bool]:
    """A run that has neither an end time nor a finished status."""
    return Run.completed_at.is_(None) & Run.status.not_in(SETTLED)


def open_db(path: str, timeout: float = 5) -> Engine:
    """statev2.sqlite read-only, a fresh connection per session (T3 writes it all the time)."""
    return create_engine(
        f'sqlite:///file:{path}?mode=ro&uri=true', poolclass=NullPool, connect_args={'timeout': timeout}
    )
