"""Read model for the steam system."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SteamView:
    drained: bool
    valve_open: bool
    baseline: float
    offset: float
    generation: int
    calibrated: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "drained": self.drained,
            "valve_open": self.valve_open,
            "baseline": self.baseline,
            "offset": self.offset,
            "generation": self.generation,
            "calibrated": self.calibrated,
        }
