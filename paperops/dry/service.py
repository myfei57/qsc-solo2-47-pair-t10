"""Dryer section: the drying procedure, drying curve and speed release.

The drain has to close, then steam is admitted, then the cylinders warm, and only
then does the section dry. Speed may only be raised once the press has made its
dewatering figure durable, and heat may only be applied once the admission valve is
open, so the order between press, steam and dry is enforced on the way in.
"""

from typing import Any, Protocol

from ..clock import LogicalClock
from ..errors import PreGateError
from ..event import EventBus, topics
from ..interlock import PreGate, StageSequence
from ..store import Journal, keys
from ..verdict import Band
from ..version import Confirmations, Generations
from . import calc
from .view import DryView

PROCEDURE_NAME = "dry.procedure"
CURVE_NAME = "dry.curve"
DRY_NAME = "dry"
STAGES = ("drain", "steam", "warm", "dry")
TEMPERATURE_KEY = "dry.temperature"


class SteamSource(Protocol):
    """Anything that can report the condensate and admission state."""

    def drained(self) -> bool: ...

    def valve_open(self) -> bool: ...


class DryService:
    """Drying procedure, drying curve and speed release."""

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
        self._slope_band = Band(0.05, 20.0)
        self._procedure = StageSequence(PROCEDURE_NAME, STAGES)
        self._press_gate = PreGate("dry.speed", journal, keys.PRESS_STATE)
        self._heat_gate = PreGate("dry.heat", journal, keys.STEAM_VALVE)
        self._valve_open = False
        self._temperature = 0.0
        self._speed = 0.0
        self._curve: dict[str, float] = {"slope": 1.0, "base": 0.0, "generation": 0}

    # ----------------------------------------------------------------- reading

    def procedure(self) -> dict[str, Any]:
        return self._procedure.state()

    def valve_open(self) -> bool:
        return self._valve_open

    def temperature(self) -> float:
        return self._temperature

    def speed(self) -> float:
        return self._speed

    def curve(self) -> dict[str, float]:
        return dict(self._curve)

    def view(self) -> DryView:
        return DryView(
            procedure=self._procedure.state(),
            valve_open=self._valve_open,
            temperature=self._temperature,
            speed=self._speed,
            slope=self._curve["slope"],
            base=self._curve["base"],
            generation=int(self._curve["generation"]),
        )

    # ------------------------------------------------------------------ writes

    def begin(self) -> dict[str, Any]:
        """Open a fresh drying procedure at the drain stage."""
        self._procedure.reset()
        return self._record_procedure("dry-begin")

    def drain_done(self) -> dict[str, Any]:
        """Close the drain stage once the header is dry."""
        self._procedure.advance("drain")
        return self._record_procedure("dry-drain")

    def admit_steam(self, steam: SteamSource) -> dict[str, Any]:
        """Admit steam; the drain has to be shut and the header reported dry."""
        if not steam.drained():
            raise PreGateError("dry: condensate is not drained")
        self._procedure.advance("steam")
        self._valve_open = True
        return self._record_procedure("dry-steam")

    def warm_up(self) -> dict[str, Any]:
        """Close the warming stage."""
        self._procedure.advance("warm")
        return self._record_procedure("dry-warm")

    def dry(self) -> dict[str, Any]:
        """Close the drying stage and mark the procedure complete."""
        self._procedure.advance("dry")
        return self._record_procedure("dry-run")

    def heat(self, target: float) -> dict[str, Any]:
        """Raise the cylinder temperature; the admission valve has to be durable."""
        self._heat_gate.require()
        if not self._valve_open:
            raise PreGateError("dry: the admission valve is not open")
        rise = calc.temperature_rise(self._temperature, target)
        self._temperature = float(target)
        tick = self._clock.tick
        row = {"temperature": self._temperature, "rise": rise, "tick": tick}
        with self._journal.transaction("dry-heat") as batch:
            self._journal.append(keys.version_key(TEMPERATURE_KEY), row, batch)
        return dict(row)

    def speed_up(self, press: Any, target: float) -> dict[str, Any]:
        """Raise the machine speed; the press dewatering figure has to be durable."""
        self._press_gate.require()
        if not press.persisted():
            raise PreGateError("dry: the press state is not durable")
        tick = self._clock.tick
        self._speed = float(target)
        row = {"speed": self._speed, "tick": tick}
        with self._journal.transaction("dry-speed") as batch:
            self._journal.append(keys.DRY_SPEED, row, batch)
        self._bus.publish(topics.TOPIC_DRY_SPEED_SET, self._speed)
        return dict(row)

    def recalibrate_curve(self, slope: float, base: float, confirmation_id: str) -> dict[str, Any]:
        """Replace the drying curve under a confirmation and a new generation."""
        self._slope_band.require(slope, "drying curve slope")
        self._confirmations.redeem(confirmation_id, CURVE_NAME, DRY_NAME)
        generation = self._generations.advance(CURVE_NAME, "dry-curve-generation")
        tick = self._clock.tick
        row = {
            "slope": float(slope),
            "base": float(base),
            "generation": generation,
            "tick": tick,
        }
        with self._journal.transaction("dry-curve") as batch:
            self._journal.append(keys.DRY_CURVE, row, batch, generation=generation)
        self._curve = {"slope": float(slope), "base": float(base), "generation": generation}
        self._bus.publish(topics.TOPIC_DRY_CURVE_SET, generation)
        return dict(row)

    def reload(self) -> DryView:
        """Restore the procedure, curve, heat and speed from the committed stream."""
        stored = self._journal.read(keys.DRY_PROCEDURE)
        if stored is not None:
            self._procedure.reset()
            for stage in stored.get("completed", []):
                self._procedure.advance(str(stage))
        valve = self._journal.read(keys.STEAM_VALVE)
        if valve is not None:
            self._valve_open = bool(valve["open"])
        heat = self._journal.read(keys.version_key(TEMPERATURE_KEY))
        if heat is not None:
            self._temperature = float(heat["temperature"])
        curve = self._journal.read(keys.DRY_CURVE)
        if curve is not None:
            self._curve = {
                "slope": float(curve["slope"]),
                "base": float(curve["base"]),
                "generation": int(curve["generation"]),
            }
        speed = self._journal.read(keys.DRY_SPEED)
        if speed is not None:
            self._speed = float(speed["speed"])
        return self.view()

    def wire(self) -> None:
        """Follow the steam valve so the dry model never drifts from the header."""
        self._bus.subscribe(topics.TOPIC_STEAM_VALVE, self._on_valve)

    # -------------------------------------------------------------- arithmetic

    def evaporation(self, temperature: float) -> float:
        return calc.evaporation(self._curve, temperature)

    def heat_duty(self, steam_flow: float) -> float:
        return calc.heat_duty(steam_flow)

    def time_to_dry(self, water_load: float, temperature: float | None = None) -> float:
        rate = self.evaporation(self._temperature if temperature is None else temperature)
        return calc.time_to_dry(rate, water_load)

    def profile_difference(self, edges: float, center: float) -> float:
        return calc.profile_difference(edges, center)

    def temperature_rise(self, target: float) -> float:
        return calc.temperature_rise(self._temperature, target)

    def steady(self, target: float) -> bool:
        return calc.steady(self._temperature, target)

    # ---------------------------------------------------------------- internals

    def _record_procedure(self, prefix: str) -> dict[str, Any]:
        state = dict(self._procedure.state())
        state["tick"] = self._clock.tick
        with self._journal.transaction(prefix) as batch:
            self._journal.append(keys.DRY_PROCEDURE, state, batch)
        self._bus.publish(topics.TOPIC_DRY_PROCEDURE, state["next"])
        return state

    def _on_valve(self, event: Any) -> None:
        self._valve_open = bool(event.payload)
