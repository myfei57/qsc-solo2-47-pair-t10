"""Size pick up and concentration arithmetic."""


def pick_up(roll_speed: float, stock_speed: float) -> float:
    """Fraction of stock speed the sizing roll carries away."""
    if stock_speed <= 0:
        return 0.0
    return float(roll_speed) / float(stock_speed)


def dose(flow: float, width: float, speed: float) -> float:
    """Glue add on per square metre."""
    area = float(width) * float(speed)
    if area <= 0:
        return 0.0
    return float(flow) / area


def diluted(concentration: float, water: float) -> float:
    """Concentration after a water addition, as a fraction of the original."""
    total = float(concentration) + float(water)
    if total <= 0:
        return 0.0
    return float(concentration) / total


def concentration_verdict(reading: float, low: float, high: float) -> str:
    if reading < low:
        return "lean"
    if reading > high:
        return "rich"
    return "in_band"


def alarm_required(reading: float, low: float, high: float, tolerance: float) -> bool:
    """Whether a reading sits outside the band plus its tolerance."""
    return reading < low - tolerance or reading > high + tolerance
