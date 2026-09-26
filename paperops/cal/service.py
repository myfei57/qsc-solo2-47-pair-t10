"""Calender stack control.

The nip may only be closed once the machine speed has settled and the press has made
its dewatering figure durable, so a nip is never applied to a machine still
accelerating. The nip record is a pre-gate for the reel, so a spool change cannot
start before the stack is loaded.
"""

from typing import Any, Protocol

from ..clock import LogicalClock
from ..errors import PreGateError
from ..event import EventBus, topics
from ..interlock import PreGate
from ..store import Journal, keys
from ..verdict import Band, HysteresisBand
from . import calc
from .view import CalView

NIP_BAND = Band(100.0, 800.0)


class SpeedSource(Protocol):
    """Anything that can report the speed the dry section settled on."""

    def speed(self) -> float: ...


class CalService:
    """Calender nip loading and machine speed."""

    def __init__(self, journal: Journal, bus: EventBus, clock: LogicalClock) -> None:
        self._journal = journal
        self._bus = bus
        self._clock = clock
        self._band = HysteresisBand(NIP_BAND.low, NIP_BAND.high, 10.0)
        self._dry_speed_gate = PreGate("cal.nip", journal, keys.DRY_SPEED)
        self._nip_closed = False
        self._nip_pressure = 0.0
        self._speed = 0.0
        self._target_speed = 0.0

    # ----------------------------------------------------------------- reading

    def nip_closed(self) -> bool:
        return self._nip_closed

    def nip_pressure(self) -> float:
        return self._nip_pressure

    def speed(self) -> float:
        return self._speed

    def target_speed(self) -> float:
        return self._target_speed

    def load(self) -> float:
        return calc.nip_load(self._nip_pressure, 6.0)

    def verdict(self) -> str:
        self._band.classify(self.load())
        return self._band.last

    def view(self) -> CalView:
        return CalView(
            nip_closed=self._nip_closed,
            nip_pressure=self._nip_pressure,
            speed=self._speed,
            target_speed=self._target_speed,
            load=self.load(),
            verdict=self.verdict(),
        )

    # ------------------------------------------------------------------ writes

    def set_speed(self, speed: float, target: float) -> dict[str, Any]:
        """Record the thread speed and where the drive is heading."""
        if speed < 0 or target < 0:
            raise PreGateError("cal: speed must not be negative")
        tick = self._clock.tick
        row = {"speed": float(speed), "target": float(target), "tick": tick}
        with self._journal.transaction("cal-speed") as batch:
            self._journal.append(keys.CAL_SPEED, row, batch)
        self._speed = float(speed)
        self._target_speed = float(target)
        self._bus.publish(topics.TOPIC_CAL_SPEED, self._speed)
        return dict(row)

    def close_nip(self, dry: SpeedSource, pressure: float) -> dict[str, Any]:
        """Close the nip; speed has to be settled and the dry section durable."""
        self._dry_speed_gate.require()
        speed = dry.speed()
        self._speed = speed
        if not calc.settled(speed, self._target_speed):
            raise PreGateError("cal: the machine speed has not settled")
        self._band.require(calc.nip_load(pressure, 6.0), "calender nip load")
        tick = self._clock.tick
        row = {"pressure": float(pressure), "speed": speed, "tick": tick}
        with self._journal.transaction("cal-nip") as batch:
            self._journal.append(keys.CAL_NIP, row, batch)
        self._nip_closed = True
        self._nip_pressure = float(pressure)
        self._bus.publish(topics.TOPIC_CAL_NIP, True)
        return dict(row)

    def open_nip(self) -> dict[str, Any]:
        tick = self._clock.tick
        with self._journal.transaction("cal-nip") as batch:
            self._journal.append(keys.CAL_NIP, {"pressure": 0.0, "tick": tick}, batch)
        self._nip_closed = False
        self._nip_pressure = 0.0
        self._bus.publish(topics.TOPIC_CAL_NIP, False)
        return {"nip_closed": False, "tick": tick}

    def reload(self) -> CalView:
        speed = self._journal.read(keys.CAL_SPEED)
        if speed is not None:
            self._speed = float(speed["speed"])
            self._target_speed = float(speed["target"])
        nip = self._journal.read(keys.CAL_NIP)
        if nip is not None:
            self._nip_pressure = float(nip["pressure"])
            self._nip_closed = self._nip_pressure > 0.0
        return self.view()

    # -------------------------------------------------------------- arithmetic

    def nip_load(self, width: float) -> float:
        return calc.nip_load(self._nip_pressure, width)

    def nip_impulse(self, dwell: float) -> float:
        return calc.nip_impulse(self._nip_pressure, dwell)

    def speed_difference(self) -> float:
        return calc.speed_difference(self._speed, self._target_speed)

    def settled(self, tolerance: float = 1.0) -> bool:
        return calc.settled(self._speed, self._target_speed, tolerance)

    def nip_verdict(self) -> str:
        return calc.nip_verdict(self.load(), self._band.low, self._band.high)
