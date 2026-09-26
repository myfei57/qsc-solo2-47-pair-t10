"""Read model for the calender stack."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CalView:
    nip_closed: bool
    nip_pressure: float
    speed: float
    target_speed: float
    load: float
    verdict: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "nip_closed": self.nip_closed,
            "nip_pressure": self.nip_pressure,
            "speed": self.speed,
            "target_speed": self.target_speed,
            "load": self.load,
            "verdict": self.verdict,
        }
