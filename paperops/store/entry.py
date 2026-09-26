"""Immutable rows of the append-only state stream."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class EntryKind(str, Enum):
    """Kind of row written to the stream."""

    PUT = "put"
    TOMBSTONE = "tombstone"


@dataclass(frozen=True)
class Entry:
    """One row of the state stream; rows are never edited in place."""

    seq: int
    kind: EntryKind
    key: str
    batch_id: str
    generation: int = 0
    value: Any = None
    reason: str = ""

    def to_row(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "kind": self.kind.value,
            "key": self.key,
            "batch_id": self.batch_id,
            "generation": self.generation,
            "value": self.value,
            "reason": self.reason,
        }

    def as_filter_row(self) -> dict[str, Any]:
        """Row shape understood by the shared record filter."""
        return {
            "key": self.key,
            "batch_id": self.batch_id,
            "generation": self.generation,
            "seq": self.seq,
            "kind": self.kind.value,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Entry":
        return cls(
            seq=int(row["seq"]),
            kind=EntryKind(row["kind"]),
            key=str(row["key"]),
            batch_id=str(row["batch_id"]),
            generation=int(row.get("generation", 0)),
            value=row.get("value"),
            reason=str(row.get("reason", "")),
        )
