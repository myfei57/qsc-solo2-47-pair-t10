"""Heat transfer and drying curve arithmetic."""

from typing import Mapping


def blend_weight(taken: int, steps: int) -> float:
    """Blend weight after taken of the declared handover steps."""
    if steps < 1:
        raise ValueError("a handover needs at least one step")
    return min(1.0, max(0.0, float(taken) / float(steps)))


def blend_curve(
    old: Mapping[str, float],
    new: Mapping[str, float],
    weight: float,
) -> dict[str, float]:
    """Linear blend between the old and the new drying curve at a weight."""
    w = float(weight)
    return {
        "slope": float(old["slope"]) + w * (float(new["slope"]) - float(old["slope"])),
        "base": float(old["base"]) + w * (float(new["base"]) - float(old["base"])),
    }


def evaporation(curve: Mapping[str, float], temperature: float) -> float:
    """Water evaporated per unit time at a cylinder temperature."""
    return float(curve["slope"]) * float(temperature) + float(curve["base"])


def heat_duty(steam_flow: float, latent: float = 2.26) -> float:
    """Heat carried into the dryers by a steam flow."""
    return float(steam_flow) * float(latent)


def time_to_dry(evaporation_rate: float, water_load: float) -> float:
    if evaporation_rate <= 0:
        return 0.0
    return float(water_load) / float(evaporation_rate)


def profile_difference(edges: float, center: float) -> float:
    """Cross direction difference between an edge and the centre."""
    return float(edges) - float(center)


def temperature_rise(current: float, target: float) -> float:
    if target <= current:
        return 0.0
    return float(target) - float(current)


def steady(current: float, target: float, tolerance: float = 0.5) -> bool:
    """True when a temperature has settled inside a tolerance of its target."""
    return abs(float(current) - float(target)) <= float(tolerance)
