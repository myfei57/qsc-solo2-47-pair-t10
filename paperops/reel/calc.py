"""Spool geometry and turn up arithmetic."""

import math


def diameter(core: float, thickness: float, wraps: float) -> float:
    """Outside diameter of a spool built from a core and a number of wraps."""
    return float(core) + 2.0 * float(thickness) * float(wraps)


def remaining(core: float, thickness: float, diameter_value: float) -> float:
    """Wraps left on a spool of a measured diameter."""
    if thickness <= 0:
        return 0.0
    return max(0.0, (float(diameter_value) - float(core)) / (2.0 * float(thickness)))


def length(core: float, thickness: float, wraps: float) -> float:
    """Web length on a spool from wrap geometry."""
    radii = [float(core) / 2.0 + float(thickness) * index for index in range(int(wraps))]
    return sum(2.0 * math.pi * radius for radius in radii) / 1000.0


def turn_up_verdict(diameter_value: float, target: float, tolerance: float = 5.0) -> str:
    if abs(float(diameter_value) - float(target)) <= float(tolerance):
        return "ready"
    return "waiting"
