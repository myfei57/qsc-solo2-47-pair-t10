"""Size press control.

The sizing roll has to be lifted before the glue pump may be stopped, and the
concentration alarm only latches once the roll is clear and the pump is stopped. A
new concentration carries a generation, so a verdict built on a superseded band is
refused until a fresh value lands.
"""

from typing import Any

from ..clock import LogicalClock
from ..errors import PreGateError
from ..event import Event, EventBus, topics
from ..interlock import Latch, PreGate
from ..store import Journal, keys
from ..verdict import Band, VerdictHistory
from ..version import Confirmations, Generations
from . import calc
from .view import GlueView

CONC_NAME = "glue.concentration"
GLUE_NAME = "glue"
CONC_BAND = Band(4.0, 14.0)
TOLERANCE = 1.0


class GlueService:
    """Sizing roll, glue pump, concentration band and alarm latch."""

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
        self._band = CONC_BAND
        self._roll_gate = PreGate("glue.stop", journal, keys.GLUE_ROLL)
        self._latch = Latch(
            "glue.concentration",
            set_conditions=("roll_lifted", "pump_stopped"),
            clear_conditions=("roll_lifted",),
        )
        self._history = VerdictHistory("glue.concentration")
        self._roll_lifted = False
        self._pump_running = False
        self._conc_cache: dict[float, str] = {}

    # ----------------------------------------------------------------- reading

    def roll_lifted(self) -> bool:
        return self._roll_lifted

    def pump_running(self) -> bool:
        return self._pump_running

    def alarm(self) -> bool:
        return self._latch.is_set

    def concentration(self) -> float:
        row = self._journal.read(keys.GLUE_CONC)
        if row is None:
            return 0.0
        return float(row["value"])

    def generation(self) -> int:
        row = self._journal.read(keys.GLUE_CONC)
        if row is None:
            return 0
        return int(row["generation"])

    def history(self) -> VerdictHistory:
        return self._history

    def verdict_of(self, reading: float) -> str:
        result = calc.concentration_verdict(reading, self._band.low, self._band.high)
        self._history.record(
            result,
            self._journal.watermark,
            self._clock.tick,
            f"reading={reading}",
        )
        return result

    def cached_verdict(self, reading: float) -> str:
        """Verdict memoised per reading; the cache is dropped when the band moves."""
        key = float(reading)
        hit = self._conc_cache.get(key)
        if hit is None:
            hit = calc.concentration_verdict(key, self._band.low, self._band.high)
            self._conc_cache[key] = hit
        return hit

    def alarm_required(self, reading: float) -> bool:
        return calc.alarm_required(reading, self._band.low, self._band.high, TOLERANCE)

    def view(self) -> GlueView:
        return GlueView(
            roll_lifted=self._roll_lifted,
            pump_running=self._pump_running,
            alarm=self.alarm(),
            concentration=self.concentration(),
            verdict=calc.concentration_verdict(
                self.concentration(), self._band.low, self._band.high
            ),
            generation=self.generation(),
        )

    # ------------------------------------------------------------------ writes

    def lift_roll(self) -> dict[str, Any]:
        tick = self._clock.tick
        with self._journal.transaction("glue-roll") as batch:
            self._journal.append(keys.GLUE_ROLL, {"lifted": True, "tick": tick}, batch)
        self._roll_lifted = True
        self._bus.publish(topics.TOPIC_GLUE_ROLL_LIFTED, tick)
        return {"roll_lifted": True, "tick": tick}

    def lower_roll(self) -> dict[str, Any]:
        tick = self._clock.tick
        with self._journal.transaction("glue-roll") as batch:
            self._journal.append(keys.GLUE_ROLL, {"lifted": False, "tick": tick}, batch)
        self._roll_lifted = False
        return {"roll_lifted": False, "tick": tick}

    def stop_pump(self) -> dict[str, Any]:
        """Stop the glue pump; the sizing roll has to be lifted first."""
        self._roll_gate.require()
        if not self._roll_lifted:
            raise PreGateError("glue: the sizing roll is not lifted")
        tick = self._clock.tick
        with self._journal.transaction("glue-pump") as batch:
            self._journal.append(keys.GLUE_PUMP, {"running": False, "tick": tick}, batch)
        self._pump_running = False
        self._bus.publish(topics.TOPIC_GLUE_PUMP_STOPPED, tick)
        return {"running": False, "tick": tick}

    def start_pump(self) -> dict[str, Any]:
        tick = self._clock.tick
        with self._journal.transaction("glue-pump") as batch:
            self._journal.append(keys.GLUE_PUMP, {"running": True, "tick": tick}, batch)
        self._pump_running = True
        return {"running": True, "tick": tick}

    def set_alarm(self) -> dict[str, Any]:
        """Latch the concentration alarm once the roll is clear and the pump stopped."""
        self._latch.set(
            {
                "roll_lifted": self._roll_lifted,
                "pump_stopped": not self._pump_running,
            }
        )
        tick = self._clock.tick
        with self._journal.transaction("glue-alarm") as batch:
            self._journal.append(keys.GLUE_ALARM, {"alarm": True, "tick": tick}, batch)
        self._bus.publish(topics.TOPIC_GLUE_ALARM, True)
        return {"alarm": True, "tick": tick}

    def clear_alarm(self) -> dict[str, Any]:
        """Clear the concentration alarm; the roll still has to be clear."""
        self._latch.clear({"roll_lifted": self._roll_lifted})
        tick = self._clock.tick
        with self._journal.transaction("glue-alarm") as batch:
            self._journal.append(keys.GLUE_ALARM, {"alarm": False, "tick": tick}, batch)
        self._bus.publish(topics.TOPIC_GLUE_ALARM, False)
        return {"alarm": False, "tick": tick}

    def set_concentration(self, value: float, confirmation_id: str) -> dict[str, Any]:
        """Adopt a new concentration under a confirmation and a new generation."""
        self._band.require(value, "glue concentration")
        self._confirmations.redeem(confirmation_id, CONC_NAME, GLUE_NAME)
        generation = self._generations.advance(CONC_NAME, "glue-conc-generation")
        tick = self._clock.tick
        row = {"value": float(value), "generation": generation, "tick": tick}
        with self._journal.transaction("glue-conc") as batch:
            self._journal.append(keys.GLUE_CONC, row, batch, generation=generation)
        self._bus.publish(topics.TOPIC_GLUE_CONC_SET, generation)
        return dict(row)

    def reload(self) -> GlueView:
        roll = self._journal.read(keys.GLUE_ROLL)
        if roll is not None:
            self._roll_lifted = bool(roll["lifted"])
        pump = self._journal.read(keys.GLUE_PUMP)
        if pump is not None:
            self._pump_running = bool(pump["running"])
        alarm = self._journal.read(keys.GLUE_ALARM)
        if alarm is not None:
            self._latch.restore(bool(alarm["alarm"]))
        return self.view()

    def wire(self) -> None:
        """Drop the verdict cache whenever the concentration band moves."""
        self._bus.subscribe(topics.TOPIC_GLUE_CONC_SET, self._on_band_change)

    # -------------------------------------------------------------- arithmetic

    def pick_up(self, roll_speed: float, stock_speed: float) -> float:
        return calc.pick_up(roll_speed, stock_speed)

    def dose(self, flow: float, width: float, speed: float) -> float:
        return calc.dose(flow, width, speed)

    def diluted(self, concentration: float, water: float) -> float:
        return calc.diluted(concentration, water)

    # ---------------------------------------------------------------- internals

    def _on_band_change(self, event: Event) -> None:
        self._conc_cache = {}
