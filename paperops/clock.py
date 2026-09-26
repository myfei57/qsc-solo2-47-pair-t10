"""Deterministic tick and identifier sources.

The service never reads the wall clock and never draws random numbers, so every
behaviour can be reproduced from the sequence of operations alone.
"""


class LogicalClock:
    """Monotonic tick counter used in place of wall-clock time."""

    def __init__(self, start: int = 0) -> None:
        if start < 0:
            raise ValueError("clock start must not be negative")
        self._tick = start

    @property
    def tick(self) -> int:
        return self._tick

    def advance(self, steps: int = 1) -> int:
        if steps < 1:
            raise ValueError("advance requires at least one step")
        self._tick += steps
        return self._tick


def format_id(prefix: str, number: int, width: int = 6) -> str:
    """Shape an identifier from a prefix and a positive number."""
    return f"{prefix}-{number:0{width}d}"


def parse_id(text: str) -> int | None:
    """Recover the number of an identifier produced by :func:`format_id`."""
    _, _, tail = text.rpartition("-")
    if not tail.isdigit():
        return None
    return int(tail)


class IdSequence:
    """Monotonic identifier source with a fixed textual shape."""

    def __init__(self, prefix: str, width: int = 6) -> None:
        self._prefix = prefix
        self._width = width
        self._issued = 0

    def next(self) -> str:
        self._issued += 1
        return format_id(self._prefix, self._issued, self._width)

    def restore(self, issued: int) -> None:
        """Keep the counter ahead of identifiers recovered from a replayed log."""
        self._issued = max(self._issued, issued)
