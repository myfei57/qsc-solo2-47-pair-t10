"""Rolling windows and the sustained threshold rule."""

from dataclasses import dataclass
from typing import Any, Sequence

SUSTAINED = "sustained"
TRANSIENT = "transient"
INSUFFICIENT = "insufficient"

ABOVE_MODE = "above"
BELOW_MODE = "below"


class Window:
    """Fixed-size rolling buffer of the most recent samples."""

    def __init__(self, size: int) -> None:
        if size < 1:
            raise ValueError("window size must be at least one")
        self._size = int(size)
        self._values: list[float] = []

    @property
    def size(self) -> int:
        return self._size

    def __len__(self) -> int:
        return len(self._values)

    def push(self, value: float) -> None:
        self._values.append(float(value))
        if len(self._values) > self._size:
            self._values = self._values[-self._size :]

    def clear(self) -> None:
        self._values = []

    def values(self) -> tuple[float, ...]:
        return tuple(self._values)

    def average(self) -> float:
        if not self._values:
            return 0.0
        return sum(self._values) / len(self._values)

    def span(self) -> float:
        if not self._values:
            return 0.0
        return max(self._values) - min(self._values)

    def is_full(self) -> bool:
        return len(self._values) >= self._size


@dataclass(frozen=True)
class WindowVerdict:
    """Outcome of comparing a window against a threshold."""

    verdict: str
    average: float
    span: float
    samples: int
    required: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "average": self.average,
            "span": self.span,
            "samples": self.samples,
            "required": self.required,
        }


def compare(values: Sequence[float], threshold: float, mode: str) -> bool:
    """True when every sample sits on the requested side of the threshold."""
    if mode not in (ABOVE_MODE, BELOW_MODE):
        raise ValueError(f"unsupported comparison mode {mode}")
    if not values:
        return False
    if mode == ABOVE_MODE:
        return all(value > threshold for value in values)
    return all(value < threshold for value in values)


class WindowEvaluator:
    """Sustained threshold rule: the verdict flips only when a full window agrees."""

    def __init__(
        self,
        window: Window,
        threshold: float,
        mode: str,
        minimum_samples: int,
    ) -> None:
        if mode not in (ABOVE_MODE, BELOW_MODE):
            raise ValueError(f"unsupported comparison mode {mode}")
        self._window = window
        self._threshold = float(threshold)
        self._mode = mode
        self._minimum = int(minimum_samples)

    @property
    def window(self) -> Window:
        return self._window

    @property
    def threshold(self) -> float:
        return self._threshold

    @property
    def mode(self) -> str:
        return self._mode

    def evaluate(self) -> WindowVerdict:
        values = self._window.values()
        if not self._window.is_full() or len(values) < self._minimum:
            verdict = INSUFFICIENT
        elif compare(values, self._threshold, self._mode):
            verdict = SUSTAINED
        else:
            verdict = TRANSIENT
        return WindowVerdict(
            verdict=verdict,
            average=self._window.average(),
            span=self._window.span(),
            samples=len(values),
            required=self._minimum,
        )

    def push(self, value: float) -> WindowVerdict:
        self._window.push(value)
        return self.evaluate()
