"""Read model for the dryer section."""

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class DryView:
    procedure: Mapping[str, Any]
    valve_open: bool
    temperature: float
    speed: float
    slope: float
    base: float
    generation: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "procedure": dict(self.procedure),
            "valve_open": self.valve_open,
            "temperature": self.temperature,
            "speed": self.speed,
            "slope": self.slope,
            "base": self.base,
            "generation": self.generation,
        }
