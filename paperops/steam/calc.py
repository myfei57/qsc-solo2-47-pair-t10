"""Steam pressure and condensate arithmetic."""


def pressure_drop(supply: float, header: float) -> float:
    """Pressure lost between the supply main and the header."""
    return float(supply) - float(header)


def offset(reading: float, baseline: float) -> float:
    """Reading measured against the calibrated baseline."""
    return float(reading) - float(baseline)


def saturation_temperature(pressure: float) -> float:
    """Approximate saturation temperature of steam at a gauge pressure."""
    return 100.0 + float(pressure) * 0.62


def condensate_load(flow: float, dryness_fraction: float) -> float:
    """Condensate carried by wet steam at a dryness fraction."""
    fraction = max(0.0, min(1.0, float(dryness_fraction)))
    return float(flow) * (1.0 - fraction)


def verdict(offset_value: float, threshold: float = 0.15) -> str:
    """Whether a pressure reading sits inside the calibration tolerance."""
    if abs(float(offset_value)) <= float(threshold):
        return "in_band"
    return "out_of_band"
