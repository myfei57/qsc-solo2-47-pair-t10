"""Current verdicts next to verdicts frozen at earlier watermarks."""

from dataclasses import dataclass
from typing import Any

UNKNOWN = "unknown"


@dataclass(frozen=True)
class VerdictPoint:
    """A verdict together with the stream position it was taken at."""

    verdict: str
    watermark: int
    tick: int
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "watermark": self.watermark,
            "tick": self.tick,
            "detail": self.detail,
        }


class VerdictHistory:
    """Keeps the current verdict alongside the verdict frozen at each watermark."""

    def __init__(self, subject: str) -> None:
        self._subject = subject
        self._points: list[VerdictPoint] = []

    @property
    def subject(self) -> str:
        return self._subject

    def record(self, verdict: str, watermark: int, tick: int, detail: str = "") -> VerdictPoint:
        point = VerdictPoint(verdict=verdict, watermark=watermark, tick=tick, detail=detail)
        self._points.append(point)
        return point

    def current(self) -> str:
        if not self._points:
            return UNKNOWN
        return self._points[-1].verdict

    def at(self, watermark: int) -> str:
        """Verdict that was current at a stream position, for historical questions."""
        verdict = UNKNOWN
        for point in self._points:
            if point.watermark <= watermark:
                verdict = point.verdict
        return verdict

    def changed_since(self, watermark: int) -> bool:
        return self.current() != self.at(watermark)

    def points(self) -> tuple[VerdictPoint, ...]:
        return tuple(self._points)

    def clear(self) -> None:
        self._points = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self._subject,
            "current": self.current(),
            "points": [point.to_dict() for point in self._points],
        }
