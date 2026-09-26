"""Dewatering arithmetic for the press section."""

from typing import Sequence


def nip_load(pressure: float, width: float) -> float:
    """Linear load carried by a press nip."""
    return float(pressure) * float(width)


def dryness(inlet_moisture: float, load: float, gain: float = 0.02) -> float:
    """Dry content after a nip, in percent, from inlet moisture and linear load."""
    removed = float(load) * float(gain)
    return max(0.0, min(100.0, 100.0 - float(inlet_moisture) + removed))


def water_removed(inlet_moisture: float, outlet_moisture: float) -> float:
    """Moisture points wrung out across the press section."""
    return float(inlet_moisture) - float(outlet_moisture)


def load_factor(load: float, rated: float) -> float:
    if rated <= 0:
        return 0.0
    return float(load) / float(rated)


def overload(load: float, rated: float, limit: float = 1.15) -> bool:
    return load_factor(load, rated) > limit


def average_dryness(readings: Sequence[float]) -> float:
    if not readings:
        return 0.0
    return sum(float(value) for value in readings) / len(readings)


def extraction(load: float, consistency: float) -> float:
    """Solids captured by the press at a given stock consistency."""
    if consistency <= 0:
        return 0.0
    return float(load) * float(consistency) / 100.0
