"""Nip and speed arithmetic for the calender stack."""


def nip_load(pressure: float, width: float) -> float:
    """Linear load carried by a calender nip."""
    return float(pressure) * float(width)


def nip_impulse(pressure: float, dwell: float) -> float:
    """Pressure integrated over the dwell time in the nip."""
    return float(pressure) * float(dwell)


def speed_difference(actual: float, target: float) -> float:
    return float(actual) - float(target)


def settled(actual: float, target: float, tolerance: float = 1.0) -> bool:
    return abs(speed_difference(actual, target)) <= float(tolerance)


def nip_verdict(load: float, low: float, high: float) -> str:
    if load < low:
        return "light"
    if load > high:
        return "heavy"
    return "in_band"
