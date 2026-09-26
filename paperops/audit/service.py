"""Event capture and querying."""

from typing import Any

from ..clock import LogicalClock
from ..event import Event, EventBus
from ..verdict import RecordFilter
from . import query, summary
from .log import AuditLog
from .record import AuditRecord


class AuditService:
    """Records every published control event and answers filtered history queries."""

    def __init__(self, log: AuditLog, bus: EventBus, clock: LogicalClock) -> None:
        self._log = log
        self._bus = bus
        self._clock = clock

    def wire(self) -> None:
        """Capture every event published on the bus."""
        self._bus.subscribe("", self._capture)

    def record(
        self,
        topic: str,
        payload: Any,
        generation: int = 0,
        batch_id: str = "",
    ) -> AuditRecord:
        return self._log.append(
            topic,
            payload,
            self._clock.tick,
            generation=generation,
            batch_id=batch_id,
        )

    def records(self) -> tuple[AuditRecord, ...]:
        return self._log.records()

    def query(self, record_filter: RecordFilter, limit: int = 0) -> list[AuditRecord]:
        return query.select(self._log.records(), record_filter, limit)

    def by_topic(self, topic: str, limit: int = 0) -> list[AuditRecord]:
        return self.query(RecordFilter(topic=topic), limit)

    def news(self, limit: int = 0) -> list[AuditRecord]:
        records = query.newest_first(self._log.records())
        if limit > 0:
            records = records[:limit]
        return records

    def summary(self) -> dict[str, Any]:
        return summary.summarize(self._log.records())

    def count(self, topic: str) -> int:
        return self._log.count(topic)

    def clear(self) -> int:
        return self._log.clear()

    @property
    def sequence(self) -> int:
        return self._log.sequence

    def _capture(self, event: Event) -> None:
        self._log.append(event.topic, event.payload, self._clock.tick)
