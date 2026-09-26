"""One row of the event record stream."""

from dataclasses import dataclass
from typing import Any, Mapping

EVENT_KIND = "event"


@dataclass(frozen=True)
class AuditRecord:
    """A control event exactly as it was observed."""

    seq: int
    record_id: str
    topic: str
    tick: int
    generation: int
    batch_id: str
    payload: Any

    def to_row(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "record_id": self.record_id,
            "topic": self.topic,
            "tick": self.tick,
            "generation": self.generation,
            "batch_id": self.batch_id,
            "payload": self.payload,
        }

    def as_filter_row(self) -> dict[str, Any]:
        """Row shape understood by the shared record filter."""
        return {
            "topic": self.topic,
            "batch_id": self.batch_id,
            "generation": self.generation,
            "seq": self.seq,
            "kind": EVENT_KIND,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "AuditRecord":
        return cls(
            seq=int(row["seq"]),
            record_id=str(row["record_id"]),
            topic=str(row["topic"]),
            tick=int(row["tick"]),
            generation=int(row.get("generation", 0)),
            batch_id=str(row.get("batch_id", "")),
            payload=row.get("payload"),
        )
