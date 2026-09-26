"""Limit bands used for range checks and verdict classification."""

from ..errors import OutOfRangeError

WITHIN = "within"
BELOW = "below"
ABOVE = "above"


class Band:
    """Inclusive limit pair."""

    def __init__(self, low: float, high: float) -> None:
        if low > high:
            raise ValueError("band low must not exceed band high")
        self._low = float(low)
        self._high = float(high)

    @property
    def low(self) -> float:
        return self._low

    @property
    def high(self) -> float:
        return self._high

    def contains(self, value: float) -> bool:
        return self._low <= value <= self._high

    def classify(self, value: float) -> str:
        if value < self._low:
            return BELOW
        if value > self._high:
            return ABOVE
        return WITHIN

    def require(self, value: float, label: str) -> float:
        if not self.contains(value):
            raise OutOfRangeError(
                f"{label} {value} is outside [{self._low}, {self._high}]"
            )
        return value


class HysteresisBand(Band):
    """Keeps the previous verdict while the value stays inside the tolerance band."""

    def __init__(self, low: float, high: float, tolerance: float) -> None:
        super().__init__(low, high)
        if tolerance < 0:
            raise ValueError("tolerance must not be negative")
        self._tolerance = float(tolerance)
        self._last = WITHIN

    @property
    def last(self) -> str:
        return self._last

    def classify(self, value: float) -> str:
        if value > self._high + self._tolerance:
            self._last = ABOVE
        elif value < self._low - self._tolerance:
            self._last = BELOW
        return self._last
