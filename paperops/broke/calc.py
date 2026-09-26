"""Broke volume and recovery arithmetic."""


def broke_rate(volume: float, seconds: float) -> float:
    """Broke generated per second over a handling window."""
    if seconds <= 0:
        return 0.0
    return float(volume) / float(seconds)


def recovery(recovered: float, generated: float) -> float:
    """Fraction of generated broke that came back to the pulper."""
    if generated <= 0:
        return 0.0
    return float(recovered) / float(generated)


def reprocessed(volume: float, consistency: float) -> float:
    """Dry solids returned by a repulped broke volume."""
    return float(volume) * float(consistency) / 100.0


def latch_verdict(processed: bool, recovered: float, generated: float) -> str:
    if not processed:
        return "held"
    if recovery(recovered, generated) < 0.5:
        return "partial"
    return "cleared"
