"""Read model for the reel."""

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ReelView:
    procedure: Mapping[str, Any]
    spool_id: str
    spool_loaded: bool
    retracted: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "procedure": dict(self.procedure),
            "spool_id": self.spool_id,
            "spool_loaded": self.spool_loaded,
            "retracted": self.retracted,
        }
