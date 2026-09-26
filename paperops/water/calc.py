"""Moisture profile arithmetic."""

from typing import Mapping, Sequence

LOW = "low"
HIGH = "high"
IN_BAND = "in_band"


def default_sensors() -> dict[str, float]:
    """Positions of a freshly commissioned scanner, in metres from the front edge."""
    return {"front": 0.4, "middle": 3.1, "back": 5.8}


def validate_sensors(sensors: Mapping[str, float]) -> dict[str, float]:
    """Reject an empty map and keep positions ordered and non-negative."""
    if not sensors:
        raise ValueError("a sensor map must declare at least one sensor")
    checked: dict[str, float] = {}
    for name, position in sensors.items():
        value = float(position)
        if value < 0:
            raise ValueError(f"sensor {name} has a negative position")
        checked[str(name)] = value
    return checked


def average(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(float(value) for value in values) / len(values)


def span(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return max(values) - min(values)


def edge_center(edges: Sequence[float], center: float) -> float:
    """Difference between the mean of the edges and the centre of the web."""
    return average(edges) - float(center)


def verdict(reading: float, low: float, high: float) -> str:
    if reading < low:
        return LOW
    if reading > high:
        return HIGH
    return IN_BAND


def interpolate(points: Sequence[tuple[float, float]], position: float) -> float:
    """Linear interpolation of a profile at a position, clamped to the ends."""
    if not points:
        return 0.0
    ordered = sorted(points)
    if position <= ordered[0][0]:
        return ordered[0][1]
    if position >= ordered[-1][0]:
        return ordered[-1][1]
    for (x0, y0), (x1, y1) in zip(ordered, ordered[1:]):
        if x0 <= position <= x1:
            if x1 == x0:
                return y0
            ratio = (position - x0) / (x1 - x0)
            return y0 + (y1 - y0) * ratio
    return ordered[-1][1]
