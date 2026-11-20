"""Explicit state machines for the companion's records (plain dicts, saved as JSON by state.py).

Each Machine names its states and the moves between them; a record changes state only through move(), and any move
not listed raises IllegalStateError: a bug, never something to work around. machine.py (tasks), ledger.py (items)
and the machines below are the whole of the companion's lifecycle state."""

from collections.abc import Mapping, MutableMapping
from typing import Any, cast

from .shapes import Ask, Draft, Poll, Retry, ReviewEntry


class IllegalStateError(ValueError):
    """A state or move a machine does not allow."""


class Machine[R: Mapping[str, Any]]:
    """States and moves of one kind of record (R, a shapes.py TypedDict), kept in `record[field]`."""

    def __init__(self, name: str, moves: Mapping[str, tuple[str, ...]], field: str = 'state') -> None:
        self.name, self.field = name, field
        self.moves = {k: frozenset(v) for k, v in moves.items()}
        self.states = frozenset(self.moves)
        for to in self.moves.values():
            if not to <= self.states:
                raise IllegalStateError(f'{name}: a move to an unknown state {sorted(to - self.states)}')

    def of(self, record: R) -> str:
        s = record.get(self.field)
        if s not in self.states:
            raise IllegalStateError(f'{self.name} in no known state: {s!r}')
        return s

    def is_(self, record: R, *states: str) -> bool:
        return self.of(record) in states

    def _set(self, record: R, state: str) -> None:
        cast(MutableMapping[str, Any], record)[self.field] = state  # a TypedDict takes no key named at runtime

    def start(self, record: R, state: str) -> None:
        if state not in self.states:
            raise IllegalStateError(f'{self.name} cannot start as {state!r}')
        self._set(record, state)

    def can(self, record: R, to: str) -> bool:
        return to in self.moves[self.of(record)]

    def move(self, record: R, to: str) -> None:
        old = self.of(record)
        if to not in self.moves[old]:
            raise IllegalStateError(f'{self.name}: {old} -> {to}')
        self._set(record, to)


# A product-update draft (drafts.py), by its folder.
#   pending   previewed to the owner, not posted
#   posted    in the channel
#   revising  the owner asked to change the posted update; a chat is rewriting it
#   editing   the rewrite is previewed: update the post in place, or keep it
#   discarded the owner threw the draft away
DRAFT: Machine[Draft] = Machine(
    'draft',
    {
        'pending': ('posted', 'discarded'),
        'posted': ('revising',),
        'revising': ('editing',),
        'editing': ('posted',),
        'discarded': (),
    },
    field='status',
)

# An ask in the requests channel (inbox.py): the owner approves or declines it once.
ASK: Machine[Ask] = Machine(
    'ask', {'pending': ('approved', 'declined'), 'approved': (), 'declined': ()}, field='status'
)

# A pull request in a review batch (reviews.py), as its card line shows it.
#   queued     waiting for a free slot          reviewing  its chat is running
#   waiting    the chat asked the owner         paused     the chat waits out a usage limit
#   asked      the run ended on a question      approved | changes  the review was published
#   failed     it couldn't start, or ended without publishing           stopped  someone stopped it
# asked and failed reopen when the chat runs again (answered, or resumed), or end otherwise after all; a published
# review publishes again when its chat is re-run.
_LIVE = ('reviewing', 'waiting', 'paused')
_ENDS = ('approved', 'changes', 'failed', 'stopped', 'asked')
REVIEW: Machine[ReviewEntry] = Machine(
    'review',
    {
        'queued': ('reviewing', 'failed'),
        **{s: tuple(x for x in _LIVE + _ENDS if x != s) for s in (*_LIVE, 'asked', 'failed')},
        'approved': ('approved', 'changes'),
        'changes': ('approved', 'changes'),
        'stopped': (),
    },
)
REVIEW_ENDS = _ENDS  # a review in one of these has a verdict

# A task's automatic retry after a transient model failure (tasks.retry_transient), task['retry']: {state, count, at}.
#   idle     nothing pending (count: the retries this turn so far)
#   waiting  "continue" is due at `at`
#   sent     "continue" went at `at`; the chat gets a grace period to start running before anything else is decided
RETRY: Machine[Retry] = Machine('retry', {'idle': ('waiting',), 'waiting': ('sent', 'idle'), 'sent': ('idle',)})

# A poll (polls.py): open until it closes, by its time, the owner, or the hub.
POLL: Machine[Poll] = Machine('poll', {'open': ('closed',), 'closed': ()})
