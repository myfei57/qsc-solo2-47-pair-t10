"""A grade-change handover that overlaps the old and the new drying curve.

The dryer row shares one steam pressure and therefore one drying curve, so a grade
change cannot swap curves atomically without stopping the section. A handover runs
both curves in parallel: the effective curve is the blend of old and new weighted
by a progress fraction alpha that walks from zero to one over a fixed count of
ticks. The rules are fixed:

* Authority — exactly one effective curve exists at any moment: the committed
  curve while no handover is open, the blend while one runs, and the frozen blend
  while one is suspended. The new curve alone becomes authoritative only when the
  handover commits.
* Done — a handover commits once alpha reaches one and the section temperature
  then stays inside the tolerance of the reference temperature for the whole
  confirmation streak. Leaving the band resets the streak, never alpha.
* Lock — while a handover is open the curve target cannot move again; a second
  handover, a direct recalibration or a procedure restart are all refused.
* Interruption — a suspended handover freezes alpha and the blend. It resumes
  where it stopped, commits on the spot when the temperature still matches the
  frozen one, or aborts back to the committed curve; none of these restarts the
  drying procedure.
"""

from typing import Any, Mapping

from ..errors import NoHandoverError, PreGateError

BLENDING = "blending"
CONFIRM = "confirm"
SUSPENDED = "suspended"
COMMITTED = "committed"
ABORTED = "aborted"

RUNNING_STATES = (BLENDING, CONFIRM)
OPEN_STATES = RUNNING_STATES + (SUSPENDED,)


class CurveHandover:
    """One overlap between the committed drying curve and its replacement."""

    def __init__(
        self,
        handover_id: str,
        old_curve: Mapping[str, float],
        new_curve: Mapping[str, float],
        blend_ticks: int,
        confirm_ticks: int,
        tolerance: float,
        started_tick: int,
    ) -> None:
        if blend_ticks < 1:
            raise ValueError("blend_ticks must be at least one tick")
        if confirm_ticks < 1:
            raise ValueError("confirm_ticks must be at least one tick")
        if tolerance < 0:
            raise ValueError("tolerance must not be negative")
        self._handover_id = handover_id
        self._old = {
            "slope": float(old_curve["slope"]),
            "base": float(old_curve["base"]),
            "generation": int(old_curve.get("generation", 0)),
        }
        self._new = {"slope": float(new_curve["slope"]), "base": float(new_curve["base"])}
        self._blend_ticks = int(blend_ticks)
        self._confirm_ticks = int(confirm_ticks)
        self._tolerance = float(tolerance)
        self._started_tick = int(started_tick)
        self._state = BLENDING
        self._progress = 0
        self._confirm_reference: float | None = None
        self._confirm_streak = 0
        self._resume_state: str | None = None
        self._frozen_temperature: float | None = None
        self._finished_tick: int | None = None
        self._reason = ""

    # ------------------------------------------------------------------ reads

    @property
    def handover_id(self) -> str:
        return self._handover_id

    @property
    def state(self) -> str:
        return self._state

    @property
    def open(self) -> bool:
        """True while the handover still holds the curve target lock."""
        return self._state in OPEN_STATES

    @property
    def running(self) -> bool:
        """True while the handover can still be advanced by a tick."""
        return self._state in RUNNING_STATES

    @property
    def alpha(self) -> float:
        """Blend weight of the new curve; one means the overlap has walked over."""
        return min(1.0, self._progress / self._blend_ticks)

    @property
    def new_curve(self) -> dict[str, float]:
        return dict(self._new)

    def effective(self) -> dict[str, float]:
        """The one curve that is authoritative in the current state."""
        if self._state == COMMITTED:
            return dict(self._new)
        if self._state == ABORTED:
            return {"slope": self._old["slope"], "base": self._old["base"]}
        alpha = self.alpha
        return {
            "slope": (1.0 - alpha) * self._old["slope"] + alpha * self._new["slope"],
            "base": (1.0 - alpha) * self._old["base"] + alpha * self._new["base"],
        }

    def authority(self) -> str:
        """A short name for whoever the effective curve answers to right now."""
        if self._state in RUNNING_STATES:
            return "blend"
        if self._state == SUSPENDED:
            return "frozen-blend"
        if self._state == COMMITTED:
            return "new-curve"
        return "old-curve"

    # ----------------------------------------------------------------- writes

    def advance(self, temperature: float, tick: int) -> str:
        """Move the overlap one tick; only a running handover can advance."""
        if self._state == SUSPENDED:
            raise PreGateError(f"dry: handover {self._handover_id} is suspended")
        if self._state not in RUNNING_STATES:
            raise NoHandoverError(
                f"dry: handover {self._handover_id} is already {self._state}"
            )
        if self._state == BLENDING:
            self._progress += 1
            if self._progress >= self._blend_ticks:
                self._state = CONFIRM
                self._confirm_reference = float(temperature)
                self._confirm_streak = 0
        else:
            if abs(float(temperature) - self._confirm_reference) <= self._tolerance:
                self._confirm_streak += 1
            else:
                self._confirm_streak = 0
            if self._confirm_streak >= self._confirm_ticks:
                self._state = COMMITTED
                self._finished_tick = int(tick)
        return self._state

    def suspend(self, reason: str, temperature: float, tick: int) -> str:
        """Freeze a running handover where it stands; the blend stays authoritative."""
        if self._state == SUSPENDED:
            raise PreGateError(f"dry: handover {self._handover_id} is already suspended")
        if self._state not in RUNNING_STATES:
            raise NoHandoverError(
                f"dry: handover {self._handover_id} is already {self._state}"
            )
        self._resume_state = self._state
        self._state = SUSPENDED
        self._frozen_temperature = float(temperature)
        self._reason = str(reason)
        return self._state

    def resume(self) -> str:
        """Continue a suspended handover from the frozen point, never from zero."""
        if self._state != SUSPENDED:
            raise PreGateError(f"dry: handover {self._handover_id} is not suspended")
        self._state = self._resume_state or BLENDING
        self._resume_state = None
        return self._state

    def complete_now(self, temperature: float, tick: int) -> str:
        """Commit a suspended handover on the spot when the section has not moved."""
        if self._state != SUSPENDED:
            raise PreGateError(f"dry: handover {self._handover_id} is not suspended")
        if (
            self._frozen_temperature is None
            or abs(float(temperature) - self._frozen_temperature) > self._tolerance
        ):
            raise PreGateError("dry: temperature has left the frozen handover point")
        self._state = COMMITTED
        self._finished_tick = int(tick)
        return self._state

    def abort(self, reason: str, tick: int) -> str:
        """Give the overlap up; the committed curve stays authoritative throughout."""
        if self._state not in OPEN_STATES:
            raise NoHandoverError(
                f"dry: handover {self._handover_id} is already {self._state}"
            )
        self._state = ABORTED
        self._reason = str(reason)
        self._finished_tick = int(tick)
        return self._state

    # ---------------------------------------------------------- serialization

    def to_row(self, tick: int) -> dict[str, Any]:
        return {
            "handover_id": self._handover_id,
            "state": self._state,
            "old": dict(self._old),
            "new": dict(self._new),
            "blend_ticks": self._blend_ticks,
            "confirm_ticks": self._confirm_ticks,
            "tolerance": self._tolerance,
            "progress": self._progress,
            "alpha": self.alpha,
            "confirm_reference": self._confirm_reference,
            "confirm_streak": self._confirm_streak,
            "resume_state": self._resume_state,
            "frozen_temperature": self._frozen_temperature,
            "started_tick": self._started_tick,
            "finished_tick": self._finished_tick,
            "reason": self._reason,
            "authority": self.authority(),
            "effective": self.effective(),
            "tick": int(tick),
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "CurveHandover":
        handover = cls(
            handover_id=str(row["handover_id"]),
            old_curve=row["old"],
            new_curve=row["new"],
            blend_ticks=int(row["blend_ticks"]),
            confirm_ticks=int(row["confirm_ticks"]),
            tolerance=float(row["tolerance"]),
            started_tick=int(row["started_tick"]),
        )
        handover._state = str(row["state"])
        handover._progress = int(row["progress"])
        handover._confirm_reference = row["confirm_reference"]
        handover._confirm_streak = int(row["confirm_streak"])
        handover._resume_state = row["resume_state"]
        handover._frozen_temperature = row["frozen_temperature"]
        handover._finished_tick = row["finished_tick"]
        handover._reason = str(row.get("reason", ""))
        return handover
