"""Filtering rules shared by every record query path."""

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class RecordFilter:
    """Narrowing rules applied to record rows."""

    topic: str | None = None
    key_prefix: str | None = None
    batch_id: str | None = None
    min_generation: int | None = None
    min_seq: int | None = None
    max_seq: int | None = None
    kinds: tuple[str, ...] = ()

    def matches(self, row: Mapping[str, Any]) -> bool:
        if self.topic is not None and row.get("topic") != self.topic:
            return False
        if self.key_prefix is not None and not str(row.get("key", "")).startswith(self.key_prefix):
            return False
        if self.batch_id is not None and row.get("batch_id") != self.batch_id:
            return False
        if self.min_generation is not None and int(row.get("generation", 0)) < self.min_generation:
            return False
        if self.min_seq is not None and int(row.get("seq", 0)) < self.min_seq:
            return False
        if self.max_seq is not None and int(row.get("seq", 0)) > self.max_seq:
            return False
        if self.kinds and str(row.get("kind", "")) not in self.kinds:
            return False
        return True

    def apply(self, rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        return [row for row in rows if self.matches(row)]

    def describe(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "key_prefix": self.key_prefix,
            "batch_id": self.batch_id,
            "min_generation": self.min_generation,
            "min_seq": self.min_seq,
            "max_seq": self.max_seq,
            "kinds": list(self.kinds),
        }


def _int_or_none(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    return int(raw)


def parse_filter(params: Mapping[str, str]) -> RecordFilter:
    """Build a filter from request query parameters."""
    kinds: Sequence[str] = tuple(
        part.strip() for part in str(params.get("kind", "")).split(",") if part.strip()
    )
    return RecordFilter(
        topic=params.get("topic") or None,
        key_prefix=params.get("key_prefix") or None,
        batch_id=params.get("batch_id") or None,
        min_generation=_int_or_none(params.get("min_generation")),
        min_seq=_int_or_none(params.get("min_seq")),
        max_seq=_int_or_none(params.get("max_seq")),
        kinds=kinds,
    )
