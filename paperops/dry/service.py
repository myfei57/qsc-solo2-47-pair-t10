"""Dryer section: the drying procedure, drying curve and speed release.

The drain has to close, then steam is admitted, then the cylinders warm, and only
then does the section dry. Speed may only be raised once the press has made its
dewatering figure durable, and heat may only be applied once the admission valve is
open, so the order between press, steam and dry is enforced on the way in.

Grade changes do not stop the section: a curve handover overlaps the old and the
new curve and closes under its own rules (see ``dry.handover``).
"""

from typing import Any, Protocol

from ..clock import LogicalClock
from ..errors import HandoverInProgressError, NoHandoverError, PreGateError
from ..event import EventBus, topics
from ..interlock import PreGate, StageSequence
from ..store import Journal, keys
from ..verdict import Band
from ..version import Confirmations, Generations
from . import calc
from .handover import COMMITTED, CurveHandover
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
        self._handover: CurveHandover | None = None

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

    def effective_curve(self) -> dict[str, float]:
        """The one curve that is authoritative right now.

        An open handover answers with its blend (frozen while suspended); anything
        else answers with the committed curve.
        """
        if self._handover is not None and self._handover.open:
            return self._handover.effective()
        return dict(self._curve)

    def handover(self) -> dict[str, Any] | None:
        """The current handover record, open or closed, when one exists."""
        if self._handover is None:
            return None
        return self._handover.to_row(self._clock.tick)

    def view(self) -> DryView:
        return DryView(
            procedure=self._procedure.state(),
            valve_open=self._valve_open,
            temperature=self._temperature,
            speed=self._speed,
            slope=self._curve["slope"],
            base=self._curve["base"],
            generation=int(self._curve["generation"]),
            effective=self.effective_curve(),
            handover=self.handover(),
        )

    # ------------------------------------------------------------------ writes

    def begin(self) -> dict[str, Any]:
        """Open a fresh drying procedure at the drain stage.

        Refused while a curve handover is open: the handover has to be wrapped up
        (resumed to a commit, completed on the spot, or aborted) before the
        procedure may start over, so an interrupted grade change can never be
        escaped by re-running the whole drying procedure.
        """
        self._require_no_open_handover()
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
        """Replace the drying curve under a confirmation and a new generation.

        Refused while a handover is open: the curve target stays locked until the
        running handover closes.
        """
        self._require_no_open_handover()
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

    # -------------------------------------------------------------- handover

    def begin_handover(
        self,
        slope: float,
        base: float,
        confirmation_id: str,
        blend_ticks: int = 5,
        confirm_ticks: int = 3,
        tolerance: float = 0.5,
    ) -> dict[str, Any]:
        """Open a grade-change handover toward a new curve; one at a time.

        The old and the new curve run in parallel from here on: the effective
        curve is their blend, and the target stays locked until the handover
        closes. The committed curve row is only rewritten when it commits.
        """
        self._require_no_open_handover()
        self._slope_band.require(slope, "drying curve slope")
        self._confirmations.redeem(confirmation_id, CURVE_NAME, DRY_NAME)
        sequence = len(self._journal.history(keys.DRY_HANDOVER)) + 1
        self._handover = CurveHandover(
            handover_id=f"hov-{sequence:04d}",
            old_curve=self._curve,
            new_curve={"slope": float(slope), "base": float(base)},
            blend_ticks=int(blend_ticks),
            confirm_ticks=int(confirm_ticks),
            tolerance=float(tolerance),
            started_tick=self._clock.tick,
        )
        return self._record_handover("dry-handover-begin")

    def tick_handover(self) -> dict[str, Any]:
        """Advance the open handover one tick against the current temperature."""
        handover = self._require_open_handover()
        handover.advance(self._temperature, self._clock.tick)
        if handover.state == COMMITTED:
            return self._commit_handover()
        return self._record_handover("dry-handover-tick")

    def suspend_handover(self, reason: str = "operator") -> dict[str, Any]:
        """Freeze the open handover where it stands, keeping the frozen blend."""
        handover = self._require_open_handover()
        handover.suspend(reason, self._temperature, self._clock.tick)
        return self._record_handover("dry-handover-suspend")

    def resume_handover(self) -> dict[str, Any]:
        """Continue a suspended handover from the frozen point, never from zero."""
        handover = self._require_open_handover()
        handover.resume()
        return self._record_handover("dry-handover-resume")

    def complete_handover(self) -> dict[str, Any]:
        """Commit a suspended handover on the spot when the section has not moved."""
        handover = self._require_open_handover()
        handover.complete_now(self._temperature, self._clock.tick)
        return self._commit_handover()

    def abort_handover(self, reason: str = "operator abort") -> dict[str, Any]:
        """Give the overlap up; the committed curve stays in force throughout."""
        handover = self._require_open_handover()
        handover.abort(reason, self._clock.tick)
        return self._record_handover("dry-handover-abort")

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
        handover = self._journal.read(keys.DRY_HANDOVER)
        if handover is not None:
            restored = CurveHandover.from_row(handover)
            if restored.running:
                # A restart interrupts a running handover: it comes back frozen
                # and waits for a wrap-up decision instead of restarting the
                # overlap. The suspension is journaled by the next write.
                restored.suspend("restart", self._temperature, self._clock.tick)
            self._handover = restored
        return self.view()

    def wire(self) -> None:
        """Follow the steam valve so the dry model never drifts from the header."""
        self._bus.subscribe(topics.TOPIC_STEAM_VALVE, self._on_valve)

    # -------------------------------------------------------------- arithmetic

    def evaporation(self, temperature: float) -> float:
        return calc.evaporation(self.effective_curve(), temperature)

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

    def _record_handover(self, prefix: str) -> dict[str, Any]:
        row = self._handover.to_row(self._clock.tick)
        with self._journal.transaction(prefix) as batch:
            self._journal.append(keys.DRY_HANDOVER, row, batch)
        self._bus.publish(topics.TOPIC_DRY_HANDOVER, row["state"])
        return row

    def _commit_handover(self) -> dict[str, Any]:
        """Make the new curve the committed curve and close the handover as one unit."""
        generation = self._generations.advance(CURVE_NAME, "dry-curve-generation")
        new = self._handover.new_curve
        tick = self._clock.tick
        self._curve = {"slope": new["slope"], "base": new["base"], "generation": generation}
        curve_row = {
            "slope": new["slope"],
            "base": new["base"],
            "generation": generation,
            "tick": tick,
        }
        handover_row = self._handover.to_row(tick)
        with self._journal.transaction("dry-handover-commit") as batch:
            self._journal.append(keys.DRY_CURVE, curve_row, batch, generation=generation)
            self._journal.append(keys.DRY_HANDOVER, handover_row, batch)
        self._bus.publish(topics.TOPIC_DRY_CURVE_SET, generation)
        self._bus.publish(topics.TOPIC_DRY_HANDOVER, handover_row["state"])
        return handover_row

    def _require_open_handover(self) -> CurveHandover:
        if self._handover is None or not self._handover.open:
            raise NoHandoverError("dry: no open curve handover")
        return self._handover

    def _require_no_open_handover(self) -> None:
        if self._handover is not None and self._handover.open:
            row = self._handover.to_row(self._clock.tick)
            raise HandoverInProgressError(
                f"dry: handover {row['handover_id']} is {row['state']} "
                f"(alpha={row['alpha']:.2f}); the curve target is locked until it closes"
            )

    def _record_procedure(self, prefix: str) -> dict[str, Any]:
        state = dict(self._procedure.state())
        state["tick"] = self._clock.tick
        with self._journal.transaction(prefix) as batch:
            self._journal.append(keys.DRY_PROCEDURE, state, batch)
        self._bus.publish(topics.TOPIC_DRY_PROCEDURE, state["next"])
        return state

    def _on_valve(self, event: Any) -> None:
        self._valve_open = bool(event.payload)
        if not self._valve_open and self._handover is not None and self._handover.running:
            # Losing steam mid-handover is an interruption, not a cancellation:
            # freeze the overlap so it can be wrapped up once steam is back.
            self.suspend_handover("steam valve closed")
