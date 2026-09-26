"""Read model for the size press."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GlueView:
    roll_lifted: bool
    pump_running: bool
    alarm: bool
    concentration: float
    verdict: str
    generation: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "roll_lifted": self.roll_lifted,
            "pump_running": self.pump_running,
            "alarm": self.alarm,
            "concentration": self.concentration,
            "verdict": self.verdict,
            "generation": self.generation,
        }
