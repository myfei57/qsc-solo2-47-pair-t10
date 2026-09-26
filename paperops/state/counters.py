"""Per topic event counters."""

from ..event import ALL_TOPICS, EventBus


def counters(bus: EventBus) -> dict[str, int]:
    """How many times each declared topic has been published."""
    return {topic: bus.count(topic) for topic in ALL_TOPICS}
