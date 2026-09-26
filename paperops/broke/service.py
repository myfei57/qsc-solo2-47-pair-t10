"""Broke handling procedure.

A break sets the handling latch and opens the procedure. Broke has to be recorded and
processed before the latch may be cleared, and the machine may only take the web back
once the latch is clear, so a fresh break can never be run over by a restart.
"""

from typing import Any, Mapping

from ..clock import LogicalClock
from ..errors import LatchClearError
from ..event import EventBus, topics
from ..interlock import Latch, StageSequence
from ..store import Journal, keys
from ..verdict import BatchRegistry, VerdictHistory
from . import calc
from .view import BrokeView

PROCEDURE_NAME = "broke.procedure"
STAGES = ("break", "process", "reset", "takeover")


class BrokeService:
    """Broke volume, handling batches and the handling latch."""

    def __init__(
        self,
        journal: Journal,
        bus: EventBus,
        clock: LogicalClock,
        batches: BatchRegistry,
    ) -> None:
        self._journal = journal
        self._bus = bus
        self._clock = clock
        self._batches = batches
        self._procedure = StageSequence(PROCEDURE_NAME, STAGES)
        self._latch = Latch(
            "broke.handling",
            set_conditions=("broken",),
            clear_conditions=("handled",),
        )
        self._history = VerdictHistory("broke.handling")
        self._handled = False

    # ----------------------------------------------------------------- reading

    def procedure(self) -> dict[str, Any]:
        return self._procedure.state()

    def latched(self) -> bool:
        return self._latch.is_set

    def handled(self) -> bool:
        return self._handled

    def history(self) -> VerdictHistory:
        return self._history

    def batches(self) -> tuple[Mapping[str, Any], ...]:
        return self._batches.entries()

    def batch_total(self) -> float:
        return sum(float(entry["volume"]) for entry in self._batches.entries())

    def view(self) -> BrokeView:
        return BrokeView(
            procedure=self._procedure.state(),
            latched=self.latched(),
            handled=self._handled,
            total=self.batch_total(),
        )

    # ------------------------------------------------------------------ writes

    def trip(self, reason: str) -> dict[str, Any]:
        """Register a web break and latch handling."""
        self._procedure.reset()
        self._procedure.advance("break")
        self._handled = False
        self._latch.set({"broken": True})
        tick = self._clock.tick
        row = {"latched": True, "reason": reason, "tick": tick}
        with self._journal.transaction("broke-trip") as batch:
            self._journal.append(keys.BROKE_LATCH, row, batch)
        self._record_procedure("broke-break")
        self._bus.publish(topics.TOPIC_BROKE_LATCH, True)
        return dict(row)

    def process(self, volume: float, batch_id: str) -> dict[str, Any]:
        """Record a handled broke batch; the break has to be registered first."""
        self._procedure.advance("process")
        self._batches.reserve(
            batch_id,
            {
                "volume": float(volume),
                "tick": self._clock.tick,
            },
        )
        self._handled = True
        self._history.record(
            "processed",
            self._journal.watermark,
            self._clock.tick,
            f"volume={volume}",
        )
        self._record_procedure("broke-process")
        self._bus.publish(topics.TOPIC_BROKE_HANDLED, batch_id)
        return {"batch_id": batch_id, "volume": float(volume), "total": self.batch_total()}

    def reset_latch(self) -> dict[str, Any]:
        """Clear the handling latch; broke has to be processed first."""
        self._latch.clear({"handled": self._handled})
        self._procedure.advance("reset")
        tick = self._clock.tick
        row = {"latched": False, "tick": tick}
        with self._journal.transaction("broke-reset") as batch:
            self._journal.append(keys.BROKE_LATCH, row, batch)
        self._record_procedure("broke-reset")
        self._bus.publish(topics.TOPIC_BROKE_LATCH, False)
        return dict(row)

    def take_over(self) -> dict[str, Any]:
        """Take the web back; the handling latch has to be clear."""
        if self._latch.is_set:
            raise LatchClearError("broke: the handling latch is still set")
        self._procedure.advance("takeover")
        self._bus.publish(topics.TOPIC_BROKE_PROCEDURE, "complete")
        return self._record_procedure("broke-takeover")

    def reload(self) -> BrokeView:
        stored = self._journal.read(keys.BROKE_PROCEDURE)
        if stored is not None:
            self._procedure.reset()
            for stage in stored.get("completed", []):
                self._procedure.advance(str(stage))
        latch = self._journal.read(keys.BROKE_LATCH)
        if latch is not None:
            self._latch.restore(bool(latch["latched"]))
        self._handled = self._procedure.is_done("process")
        return self.view()

    # -------------------------------------------------------------- arithmetic

    def broke_rate(self, volume: float, seconds: float) -> float:
        return calc.broke_rate(volume, seconds)

    def recovery(self, recovered: float, generated: float) -> float:
        return calc.recovery(recovered, generated)

    def reprocessed(self, volume: float, consistency: float) -> float:
        return calc.reprocessed(volume, consistency)

    def latch_verdict(self, recovered: float, generated: float) -> str:
        return calc.latch_verdict(self._handled, recovered, generated)

    # ---------------------------------------------------------------- internals

    def _record_procedure(self, prefix: str) -> dict[str, Any]:
        state = dict(self._procedure.state())
        state["tick"] = self._clock.tick
        with self._journal.transaction(prefix) as batch:
            self._journal.append(keys.BROKE_PROCEDURE, state, batch)
        return state
