"""Press section dewatering and the durable record that releases the drive.

The dewatering figure has to be written to the record stream before the machine may
be sped up, so a speed change is always built on a durable dryness value. The dry
section owns the gate that reads this record; the press only has to make it durable.
"""

from typing import Any, Sequence

from ..clock import LogicalClock
from ..errors import OutOfRangeError
from ..event import EventBus, topics
from ..store import Journal, keys
from ..verdict import Band, VerdictHistory
from ..version import Confirmations, Generations
from . import calc
from .view import PressView

DEWATER_NAME = "press.dewater"
PRESS_NAME = "press"
DRYNESS_BAND = Band(0.0, 100.0)
GAIN_BAND = Band(0.001, 0.2)
DEFAULT_WIDTH = 6.0


class PressService:
    """Nip loading, dewatering data and the durable press state."""

    def __init__(
        self,
        journal: Journal,
        bus: EventBus,
        clock: LogicalClock,
        generations: Generations,
        confirmations: Confirmations,
    ) -> None:
        self._journal = journal
        self._bus = bus
        self._clock = clock
        self._generations = generations
        self._confirmations = confirmations
        self._band = DRYNESS_BAND
        self._gain_band = GAIN_BAND
        self._history = VerdictHistory("press.dryness")
        self._load = 0.0
        self._gain = 0.02
        self._dryness = 0.0
        self._persisted = False
        self._persisted_tick = 0
        self._readings: list[float] = []

    # ----------------------------------------------------------------- reading

    def load(self) -> float:
        return self._load

    def set_load(self, load: float) -> None:
        if load < 0:
            raise ValueError("nip load must not be negative")
        self._load = float(load)
        self._bus.publish(topics.TOPIC_PRESS_LOAD, self._load)

    def dryness(self) -> float:
        return self._dryness

    def persisted(self) -> bool:
        return self._persisted

    def readings(self) -> tuple[float, ...]:
        return tuple(self._readings)

    def average_dryness(self) -> float:
        return calc.average_dryness(self._readings)

    def history(self) -> VerdictHistory:
        return self._history

    def view(self) -> PressView:
        return PressView(
            load=self._load,
            dryness=self._dryness,
            persisted=self._persisted,
            persisted_tick=self._persisted_tick,
            generation=self._generations.current(DEWATER_NAME),
        )

    # ------------------------------------------------------------------ writes

    def dewater(self, inlet_moisture: float, width: float) -> dict[str, Any]:
        """Compute and record the dewatering data; durability follows in persist."""
        self._band.require(inlet_moisture, "inlet moisture")
        load = calc.nip_load(self._load, width)
        outlet = calc.dryness(inlet_moisture, load, self._gain)
        row = {
            "inlet_moisture": float(inlet_moisture),
            "outlet_moisture": outlet,
            "removed": calc.water_removed(inlet_moisture, outlet),
            "load": load,
            "tick": self._clock.tick,
        }
        with self._journal.transaction("press-dewater") as batch:
            self._journal.append(keys.PRESS_DEWATER, row, batch)
        self._dryness = outlet
        self._readings.append(outlet)
        self._history.record(
            "recorded",
            self._journal.watermark,
            self._clock.tick,
            f"dryness={outlet:.2f}",
        )
        return dict(row)

    def persist(self, speed: float) -> int:
        """Make the press state durable; the dry section is gated on this value."""
        tick = self._clock.tick
        with self._journal.transaction("press-persist") as batch:
            self._journal.append(
                keys.PRESS_STATE,
                {
                    "load": self._load,
                    "dryness": self._dryness,
                    "speed": float(speed),
                    "tick": tick,
                },
                batch,
                generation=self._generations.current(DEWATER_NAME),
            )
        self._persisted = True
        self._persisted_tick = tick
        self._bus.publish(topics.TOPIC_DEWATER_PERSISTED, {"speed": float(speed), "tick": tick})
        return tick

    def recalibrate_gain(self, gain: float, confirmation_id: str) -> dict[str, Any]:
        """Replace the press gain under a confirmation and a new generation."""
        self._gain_band.require(gain, "press gain")
        self._confirmations.redeem(confirmation_id, DEWATER_NAME, PRESS_NAME)
        generation = self._generations.advance(DEWATER_NAME, "press-gain-generation")
        row = {"gain": float(gain), "generation": generation, "tick": self._clock.tick}
        with self._journal.transaction("press-gain") as batch:
            self._journal.append(keys.PRESS_GAIN, row, batch, generation=generation)
        self._gain = float(gain)
        return dict(row)

    def reload(self) -> PressView:
        """Restore press state from the committed part of the stream."""
        state = self._journal.read(keys.PRESS_STATE)
        if state is not None:
            self._load = float(state["load"])
            self._dryness = float(state["dryness"])
            self._persisted = True
            self._persisted_tick = int(state["tick"])
        dewater = self._journal.read(keys.PRESS_DEWATER)
        if dewater is not None and state is None:
            self._dryness = float(dewater["outlet_moisture"])
        gain = self._journal.read(keys.PRESS_GAIN)
        if gain is not None:
            self._gain = float(gain["gain"])
        return self.view()

    # -------------------------------------------------------------- arithmetic

    def nip_load(self, width: float = DEFAULT_WIDTH) -> float:
        return calc.nip_load(self._load, width)

    def dryness_for(
        self, inlet_moisture: float, width: float = DEFAULT_WIDTH, gain: float | None = None
    ) -> float:
        factor = self._gain if gain is None else float(gain)
        return calc.dryness(inlet_moisture, self.nip_load(width), factor)

    def water_removed(self, inlet_moisture: float, outlet_moisture: float) -> float:
        return calc.water_removed(inlet_moisture, outlet_moisture)

    def load_factor(self, rated: float, width: float = DEFAULT_WIDTH) -> float:
        return calc.load_factor(self.nip_load(width), rated)

    def overload(self, rated: float, width: float = DEFAULT_WIDTH) -> bool:
        return calc.overload(self.nip_load(width), rated)

    def extraction(self, consistency: float, width: float = DEFAULT_WIDTH) -> float:
        return calc.extraction(self.nip_load(width), consistency)

    def verify_band(self, value: float, label: str) -> float:
        return self._band.require(value, label)

    def reject_negative(self, value: float, label: str) -> float:
        if value < 0:
            raise OutOfRangeError(f"{label} must not be negative")
        return float(value)

    def spread(self, readings: Sequence[float]) -> float:
        if not readings:
            return 0.0
        return max(readings) - min(readings)
