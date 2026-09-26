"""Read model for broke handling."""

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class BrokeView:
    procedure: Mapping[str, Any]
    latched: bool
    handled: bool
    total: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "procedure": dict(self.procedure),
            "latched": self.latched,
            "handled": self.handled,
            "total": self.total,
        }
