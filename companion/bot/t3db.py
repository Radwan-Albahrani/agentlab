"""This agent's T3 database: the shared read-only models (t3schema.py, a copy of image/t3schema.py) at its path."""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import cache

from sqlalchemy import Engine
from sqlalchemy.orm import Session
from t3schema import (
    Base,
    Message,
    Project,
    Request,
    Run,
    Thread,
    TurnItem,
    answered_by_message,
    open_db,
    parent_of,
    text_of,
)

from .config import T3

__all__ = [
    'Base',
    'Message',
    'Project',
    'Request',
    'Run',
    'Thread',
    'TurnItem',
    'answered_by_message',
    'engine',
    'parent_of',
    'session',
    'text_of',
]


@cache
def engine() -> Engine:
    return open_db(f'{T3}/statev2.sqlite')


@contextmanager
def session() -> Iterator[Session]:
    with Session(engine()) as s:
        yield s
