"""Reel control and the spool transfer procedure.

The transfer walks through new spool, old retract and bite, in that order. A new
spool cannot be turned up until the calender nip is loaded, and the old spool cannot
be retracted until the new spool is loaded and durable, so a break is never invited
by pulling the finished spool too early.
"""

from typing import Any, Protocol

from ..clock import LogicalClock
from ..errors import PreGateError
from ..event import EventBus, topics
from ..interlock import PreGate, StageSequence
from ..store import Journal, keys
from . import calc
from .view import ReelView

PROCEDURE_NAME = "reel.procedure"
STAGES = ("new_spool", "retract", "bite")


class CalSource(Protocol):
    """Anything that can report whether the calender nip is loaded."""

    def nip_closed(self) -> bool: ...


class BrokeSource(Protocol):
    """Anything that can start a broke handling procedure."""

    def trip(self, reason: str) -> dict[str, Any]: ...


class ReelService:
    """Spool transfer procedure and reel state."""

    def __init__(self, journal: Journal, bus: EventBus, clock: LogicalClock) -> None:
        self._journal = journal
        self._bus = bus
        self._clock = clock
        self._procedure = StageSequence(PROCEDURE_NAME, STAGES)
        self._nip_gate = PreGate("reel.new_spool", journal, keys.CAL_NIP)
        self._spool_gate = PreGate("reel.retract", journal, keys.REEL_SPOOL)
        self._spool_id = ""
        self._spool_loaded = False
        self._retracted = False

    # ----------------------------------------------------------------- reading

    def procedure(self) -> dict[str, Any]:
        return self._procedure.state()

    def spool_id(self) -> str:
        return self._spool_id

    def spool_loaded(self) -> bool:
        return self._spool_loaded

    def retracted(self) -> bool:
        return self._retracted

    def view(self) -> ReelView:
        return ReelView(
            procedure=self._procedure.state(),
            spool_id=self._spool_id,
            spool_loaded=self._spool_loaded,
            retracted=self._retracted,
        )

    # ------------------------------------------------------------------ writes

    def begin_change(self, reason: str = "full spool") -> dict[str, Any]:
        """Trigger a transfer and open a fresh procedure."""
        self._procedure.reset()
        self._retracted = False
        state = dict(self._procedure.state())
        state["reason"] = reason
        state["tick"] = self._clock.tick
        with self._journal.transaction("reel-begin") as batch:
            self._journal.append(keys.REEL_PROCEDURE, state, batch)
        self._bus.publish(topics.TOPIC_REEL_PROCEDURE, state["next"])
        return state

    def new_spool(self, spool_id: str, cal: CalSource) -> dict[str, Any]:
        """Turn up a new spool; the calender nip has to be loaded first."""
        if not cal.nip_closed():
            raise PreGateError("reel: the calender nip is not loaded")
        self._nip_gate.require()
        self._procedure.advance("new_spool")
        tick = self._clock.tick
        row = {"spool_id": spool_id, "loaded": True, "tick": tick}
        with self._journal.transaction("reel-spool") as batch:
            self._journal.append(keys.REEL_SPOOL, row, batch)
        self._spool_id = spool_id
        self._spool_loaded = True
        self._bus.publish(topics.TOPIC_REEL_SPOOL, spool_id)
        self._record_procedure("reel-new-spool")
        return dict(row)

    def retract_old(self) -> dict[str, Any]:
        """Retract the finished spool; the new spool has to be loaded and durable."""
        self._spool_gate.require()
        if not self._spool_loaded:
            raise PreGateError("reel: the new spool is not loaded")
        self._procedure.advance("retract")
        tick = self._clock.tick
        row = {"spool_id": self._spool_id, "retracted": True, "tick": tick}
        with self._journal.transaction("reel-retract") as batch:
            self._journal.append(keys.REEL_RETRACT, row, batch)
        self._retracted = True
        self._record_procedure("reel-retract")
        return dict(row)

    def bite(self) -> dict[str, Any]:
        """Close the transfer once the web is carried on the new core."""
        self._procedure.advance("bite")
        return self._record_procedure("reel-bite")

    def trigger_break(self, broke: BrokeSource, reason: str) -> dict[str, Any]:
        """Hand a web break to the broke handling procedure."""
        return broke.trip(reason)

    def reload(self) -> ReelView:
        stored = self._journal.read(keys.REEL_PROCEDURE)
        if stored is not None:
            self._procedure.reset()
            for stage in stored.get("completed", []):
                self._procedure.advance(str(stage))
        spool = self._journal.read(keys.REEL_SPOOL)
        if spool is not None:
            self._spool_id = str(spool["spool_id"])
            self._spool_loaded = bool(spool["loaded"])
        retract = self._journal.read(keys.REEL_RETRACT)
        if retract is not None:
            self._retracted = bool(retract["retracted"])
        return self.view()

    # -------------------------------------------------------------- arithmetic

    def diameter(self, core: float, thickness: float, wraps: float) -> float:
        return calc.diameter(core, thickness, wraps)

    def remaining(self, core: float, thickness: float, diameter_value: float) -> float:
        return calc.remaining(core, thickness, diameter_value)

    def length(self, core: float, thickness: float, wraps: float) -> float:
        return calc.length(core, thickness, wraps)

    def turn_up_verdict(self, diameter_value: float, target: float) -> str:
        return calc.turn_up_verdict(diameter_value, target)

    # ---------------------------------------------------------------- internals

    def _record_procedure(self, prefix: str) -> dict[str, Any]:
        state = dict(self._procedure.state())
        state["tick"] = self._clock.tick
        with self._journal.transaction(prefix) as batch:
            self._journal.append(keys.REEL_PROCEDURE, state, batch)
        self._bus.publish(topics.TOPIC_REEL_PROCEDURE, state["next"])
        return state
