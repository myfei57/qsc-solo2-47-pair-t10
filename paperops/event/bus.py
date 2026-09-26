"""In-process publish and subscribe bus for control events."""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Event:
    """One published control event."""

    seq: int
    topic: str
    payload: Any


Handler = Callable[[Event], None]


class EventBus:
    """Keeps a sequence of published events and notifies interested handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = {}
        self._records: list[Event] = []

    def subscribe(self, topic: str, handler: Handler) -> None:
        """Register a handler; the empty topic string receives every event."""
        self._handlers.setdefault(topic, []).append(handler)

    def publish(self, topic: str, payload: Any = None) -> Event:
        event = Event(seq=len(self._records) + 1, topic=topic, payload=payload)
        self._records.append(event)
        for handler in self._handlers.get("", ()):
            handler(event)
        for handler in self._handlers.get(topic, ()):
            handler(event)
        return event

    def records(self) -> tuple[Event, ...]:
        return tuple(self._records)

    def count(self, topic: str) -> int:
        return sum(1 for event in self._records if event.topic == topic)

    @property
    def sequence(self) -> int:
        return len(self._records)
