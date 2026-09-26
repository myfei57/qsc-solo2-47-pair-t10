"""Steam admission and the pressure baseline.

Condensate has to be drained before the admission valve opens; the drain record is a
pre-gate so a valve can never be opened onto a flooded header. The pressure baseline
is a parameter set with a generation, and swapping the gauge moves the generation on,
which leaves the old baseline expired until a fresh calibration lands.
"""

from typing import Any, Mapping, Protocol

from ..clock import LogicalClock
from ..errors import PreGateError, StaleArtifactError
from ..event import EventBus, topics
from ..interlock import PreGate
from ..store import Journal, keys
from ..verdict import Band, VerdictHistory
from ..version import Confirmations, Generations
from . import calc
from .view import SteamView

BASELINE_NAME = "steam.baseline"
STEAM_NAME = "steam"
BASELINE_BAND = Band(0.5, 12.0)


class TransferSource(Protocol):
    """Anything that can report how far a spool transfer has walked."""

    def procedure(self) -> Mapping[str, Any]: ...


class SteamService:
    """Condensate drain, admission valve and pressure baseline."""

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
        self._band = BASELINE_BAND
        self._drain_gate = PreGate("steam.valve", journal, keys.STEAM_DRAIN)
        self._history = VerdictHistory("steam.pressure")
        self._drained = False
        self._valve_open = False

    # ----------------------------------------------------------------- reading

    def drained(self) -> bool:
        return self._drained

    def valve_open(self) -> bool:
        return self._valve_open

    def baseline(self) -> dict[str, Any] | None:
        return self._journal.read(keys.STEAM_BASELINE)

    def offset(self) -> float:
        row = self.baseline()
        if row is None:
            return 0.0
        return float(row["offset"])

    def generation(self) -> int:
        row = self.baseline()
        if row is None:
            return 0
        return int(row["generation"])

    def require_fresh_baseline(self) -> dict[str, Any]:
        """Return the baseline in force or refuse a verdict built on a stale one."""
        row = self.baseline()
        if row is None:
            raise StaleArtifactError("no steam pressure baseline has been calibrated")
        self._generations.require_current(
            BASELINE_NAME,
            int(row["generation"]),
            "steam pressure baseline",
        )
        return row

    def history(self) -> VerdictHistory:
        return self._history

    def view(self) -> SteamView:
        row = self.baseline()
        return SteamView(
            drained=self._drained,
            valve_open=self._valve_open,
            baseline=0.0 if row is None else float(row["baseline"]),
            offset=self.offset(),
            generation=self.generation(),
            calibrated=row is not None,
        )

    # ------------------------------------------------------------------ writes

    def drain(self) -> int:
        """Open the condensate trap and make the drain durable."""
        tick = self._clock.tick
        with self._journal.transaction("steam-drain") as batch:
            self._journal.append(
                keys.STEAM_DRAIN,
                {"drained": True, "tick": tick},
                batch,
            )
        self._drained = True
        self._bus.publish(topics.TOPIC_STEAM_DRAINED, tick)
        return tick

    def open_valve(self) -> dict[str, Any]:
        """Open the admission valve; the drain has to be durable first."""
        self._drain_gate.require()
        if not self._drained:
            raise PreGateError("steam: condensate has not been drained")
        tick = self._clock.tick
        with self._journal.transaction("steam-valve") as batch:
            self._journal.append(
                keys.STEAM_VALVE,
                {"open": True, "tick": tick},
                batch,
            )
        self._valve_open = True
        self._bus.publish(topics.TOPIC_STEAM_VALVE, True)
        return {"valve_open": True, "tick": tick}

    def close_valve(self) -> dict[str, Any]:
        tick = self._clock.tick
        with self._journal.transaction("steam-valve") as batch:
            self._journal.append(
                keys.STEAM_VALVE,
                {"open": False, "tick": tick},
                batch,
            )
        self._valve_open = False
        self._bus.publish(topics.TOPIC_STEAM_VALVE, False)
        return {"valve_open": False, "tick": tick}

    def close_for_stop(self, reel: TransferSource) -> dict[str, Any]:
        """Shut steam for an orderly stop; the spool transfer has to be finished."""
        procedure = reel.procedure()
        if procedure.get("next") != "complete":
            raise PreGateError("steam: the spool transfer has not finished")
        row = self.close_valve()
        row["order"] = "reel-complete"
        return row

    def calibrate(self, pressure: float, confirmation_id: str) -> dict[str, Any]:
        """Adopt a new pressure baseline under a confirmation and a new generation."""
        self._band.require(pressure, "steam baseline")
        self._confirmations.redeem(confirmation_id, BASELINE_NAME, STEAM_NAME)
        generation = self._generations.advance(BASELINE_NAME, "steam-generation")
        tick = self._clock.tick
        row = {
            "baseline": float(pressure),
            "offset": float(pressure),
            "generation": generation,
            "tick": tick,
        }
        with self._journal.transaction("steam-calibrate") as batch:
            self._journal.append(keys.STEAM_BASELINE, row, batch, generation=generation)
        self._bus.publish(topics.TOPIC_STEAM_BASELINE_SET, generation)
        return dict(row)

    def replace_gauge(self) -> int:
        """Move the generation on so the stored baseline can no longer be used."""
        generation = self._generations.advance(BASELINE_NAME, "steam-gauge")
        self._bus.publish(topics.TOPIC_STEAM_BASELINE_INVALIDATED, generation)
        return generation

    def reload(self) -> SteamView:
        drain = self._journal.read(keys.STEAM_DRAIN)
        if drain is not None:
            self._drained = bool(drain["drained"])
        valve = self._journal.read(keys.STEAM_VALVE)
        if valve is not None:
            self._valve_open = bool(valve["open"])
        return self.view()

    # -------------------------------------------------------------- arithmetic

    def pressure_of(self, reading: float) -> str:
        value = self.offset_of(reading)
        result = calc.verdict(value)
        self._history.record(
            result,
            self._journal.watermark,
            self._clock.tick,
            f"reading={reading}",
        )
        return result

    def offset_of(self, reading: float) -> float:
        baseline = self.require_fresh_baseline()
        return calc.offset(reading, float(baseline["baseline"]))

    def pressure_drop(self, supply: float, header: float) -> float:
        return calc.pressure_drop(supply, header)

    def saturation_temperature(self, pressure: float) -> float:
        return calc.saturation_temperature(pressure)

    def condensate_load(self, flow: float, dryness_fraction: float) -> float:
        return calc.condensate_load(flow, dryness_fraction)

    def verify_band(self, value: float, label: str) -> float:
        return self._band.require(value, label)

    def window_verdict(self, offset_value: float, threshold: float) -> str:
        return calc.verdict(offset_value, threshold)
