"""Selection helpers over the event record stream."""

from typing import Sequence

from ..verdict import RecordFilter
from .record import AuditRecord


def select(
    records: Sequence[AuditRecord],
    record_filter: RecordFilter,
    limit: int = 0,
) -> list[AuditRecord]:
    """Newest first, narrowed by the shared record filter."""
    kept = [
        record
        for record in reversed(records)
        if record_filter.matches(record.as_filter_row())
    ]
    if limit > 0:
        kept = kept[:limit]
    return kept


def newest_first(records: Sequence[AuditRecord]) -> list[AuditRecord]:
    return list(reversed(records))
