"""Explicit state machines for the companion's records (plain dicts, saved as JSON by state.py).

Each Machine names its states (S, a Literal in shapes.py) and the moves between them. A record's state changes only
as `rec['state'] = MACHINE.to(rec.get('state'), new)`: to() refuses any move not listed with IllegalStateError, a
bug, never something to work around. machine.py (tasks), ledger.py (items) and the machines below are the whole of
the companion's lifecycle state."""

from collections.abc import Mapping

from .shapes import AskState, DraftState, FileState, PollState, RetryState, ReviewState, StackState


class IllegalStateError(ValueError):
    """A state or move a machine does not allow."""


class Machine[S: str]:
    """The states S of one kind of record and the moves between them."""

    def __init__(self, name: str, moves: Mapping[S, tuple[S, ...]]) -> None:
        self.name = name
        self.moves = {k: frozenset(v) for k, v in moves.items()}
        self._known: dict[str, S] = {s: s for s in self.moves}
        for to in self.moves.values():
            if not to <= self.moves.keys():
                raise IllegalStateError(f'{name}: a move to an unknown state {sorted(to - self.moves.keys())}')

    def of(self, state: str | None) -> S:
        """A stored state, checked: anything the machine doesn't name raises."""
        if state is None or state not in self._known:
            raise IllegalStateError(f'{self.name} in no known state: {state!r}')
        return self._known[state]

    def is_(self, state: str | None, *states: S) -> bool:
        return self.of(state) in states

    def first(self, state: str) -> S:
        """The state a new record starts in (or an old record is read as)."""
        return self.of(state)

    def can(self, state: str | None, to: S) -> bool:
        return to in self.moves[self.of(state)]

    def to(self, state: str | None, new: S) -> S:
        """`new`, when the machine allows the move from `state` to it."""
        old = self.of(state)
        if new not in self.moves[old]:
            raise IllegalStateError(f'{self.name}: {old} -> {new}')
        return new


# A product-update draft (drafts.py), by its folder.
#   pending   previewed to the owner, not posted
#   posted    in the channel
#   revising  the owner asked to change the posted update; a chat is rewriting it
#   editing   the rewrite is previewed: update the post in place, or keep it
#   discarded the owner threw the draft away
DRAFT: Machine[DraftState] = Machine(
    'draft',
    {
        'pending': ('posted', 'discarded'),
        'posted': ('revising',),
        'revising': ('editing',),
        'editing': ('posted',),
        'discarded': (),
    },
)

# An ask in the requests channel (inbox.py): the owner approves or declines it once.
ASK: Machine[AskState] = Machine('ask', {'pending': ('approved', 'declined'), 'approved': (), 'declined': ()})

# A pull request in a review batch (reviews.py), as its card line shows it.
#   queued     waiting for a free slot          reviewing  its chat is running
#   waiting    the chat asked the owner         paused     the chat waits out a usage limit
#   asked      the run ended on a question      approved | changes  the review was published
#   failed     it couldn't start, or ended without publishing           stopped  someone stopped it
# asked and failed reopen when the chat runs again (answered, or resumed), or end otherwise after all; a published
# review publishes again when its chat is re-run.
_LIVE: tuple[ReviewState, ...] = ('reviewing', 'waiting', 'paused')
REVIEW_ENDS: tuple[ReviewState, ...] = ('approved', 'changes', 'failed', 'stopped', 'asked')  # it has a verdict
_REOPENS: tuple[ReviewState, ...] = (*_LIVE, 'asked', 'failed')
REVIEW: Machine[ReviewState] = Machine(
    'review',
    {
        'queued': ('reviewing', 'failed'),
        **{s: tuple(x for x in _LIVE + REVIEW_ENDS if x != s) for s in _REOPENS},
        'approved': ('approved', 'changes'),
        'changes': ('approved', 'changes'),
        'stopped': (),
    },
)

# A GitHub stack under review (reviews.py, state['review_stacks']): one PR at a time, bottom up.
#   reviewing  a PR of it is queued or under review (current), or the next one is about to be taken
#   done       every open PR of it was reviewed (or already had been since it started)
#   stopped    someone stopped the review of its current PR: the rest is left alone
STACK: Machine[StackState] = Machine('stack', {'reviewing': ('done', 'stopped'), 'done': (), 'stopped': ()})

# A file the agent attached to a message (attachments.py, a ledger item's "attachments"): the gate decides the first
# state, the message's fate the last. ledger.move refuses to send a message while a file of it is still ready.
#   ready     it passed the gate (allowed type, size, in the outbox) and goes when its message goes
#   held      the gate kept it back: it never leaves
#   sent      it went with its message
#   failed    its message went, the upload did not
#   withheld  its message never went (refused, rejected, replaced, failed, dry run)
ATTACHMENT: Machine[FileState] = Machine(
    'attachment',
    {'ready': ('sent', 'failed', 'withheld'), 'held': (), 'sent': (), 'failed': (), 'withheld': ()},
)

# A task's automatic retry after a transient model failure (tasks.retry_transient), task['retry']: {state, count, at}.
#   idle     nothing pending (count: the retries this turn so far)
#   waiting  "continue" is due at `at`
#   sent     "continue" went at `at`; the chat gets a grace period to start running before anything else is decided
RETRY: Machine[RetryState] = Machine('retry', {'idle': ('waiting',), 'waiting': ('sent', 'idle'), 'sent': ('idle',)})

# A poll (polls.py): open until it closes, by its time, the owner, or the hub.
POLL: Machine[PollState] = Machine('poll', {'open': ('closed',), 'closed': ()})
