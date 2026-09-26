"""Read model for the press section."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PressView:
    load: float
    dryness: float
    persisted: bool
    persisted_tick: int
    generation: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "load": self.load,
            "dryness": self.dryness,
            "persisted": self.persisted,
            "persisted_tick": self.persisted_tick,
            "generation": self.generation,
        }
