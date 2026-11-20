"""Explicit state machines for the host programs (the same small Machine as companion/bot/fsm.py and cli/agentlab/fsm.py;
the three packages never import each other).

A Machine names its states (S, a Literal) and the moves between them. A state changes only as
`rec['state'] = MACHINE.to(rec['state'], new)`: to() refuses any move not listed with IllegalStateError, a bug, never
something to work around. watch/jobs.py (the hub's agent management jobs) uses it."""

from collections.abc import Mapping


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
