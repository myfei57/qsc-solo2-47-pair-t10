"""Deterministic clock and identifier sources."""

import pytest

from paperops.clock import IdSequence, LogicalClock, format_id, parse_id


def test_logical_clock_counts_forward():
    clock = LogicalClock()
    assert clock.tick == 0
    assert clock.advance() == 1
    assert clock.advance(4) == 5
    assert clock.tick == 5
    with pytest.raises(ValueError):
        clock.advance(0)
    with pytest.raises(ValueError):
        LogicalClock(-1)


def test_identifier_shape_round_trips():
    assert format_id("cfm", 7) == "cfm-000007"
    assert parse_id("cfm-000007") == 7
    assert parse_id("cfm-abc") is None


def test_id_sequence_never_reuses_a_number():
    sequence = IdSequence("evt")
    assert sequence.next() == "evt-000001"
    assert sequence.next() == "evt-000002"
    sequence.restore(10)
    assert sequence.next() == "evt-000011"
