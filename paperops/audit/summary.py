"""Aggregate view over the event record stream."""

from typing import Any, Sequence

from .record import AuditRecord


def summarize(records: Sequence[AuditRecord]) -> dict[str, Any]:
    """Topic counts and generation counts for the whole stream."""
    topics: dict[str, int] = {}
    generations: dict[int, int] = {}
    for record in records:
        topics[record.topic] = topics.get(record.topic, 0) + 1
        generations[record.generation] = generations.get(record.generation, 0) + 1
    return {
        "total": len(records),
        "topics": topics,
        "generations": {str(key): value for key, value in sorted(generations.items())},
    }
