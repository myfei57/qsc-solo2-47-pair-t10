"""Bands, windows, histories, record filters and process batches."""

import pytest

from paperops.errors import DuplicateBatchError, OutOfRangeError, UnknownBatchError
from paperops.verdict import (
    ABOVE,
    ABOVE_MODE,
    BELOW,
    BELOW_MODE,
    INSUFFICIENT,
    SUSTAINED,
    TRANSIENT,
    WITHIN,
    Band,
    BatchRegistry,
    HysteresisBand,
    RecordFilter,
    VerdictHistory,
    Window,
    WindowEvaluator,
    compare,
    parse_filter,
)


def test_band_classifies_and_requires():
    band = Band(4.0, 14.0)
    assert band.contains(4.0) is True
    assert band.classify(2.0) == BELOW
    assert band.classify(6.0) == WITHIN
    assert band.classify(20.0) == ABOVE
    with pytest.raises(OutOfRangeError):
        band.require(20.0, "glue concentration")
    assert band.low == 4.0 and band.high == 14.0
    with pytest.raises(ValueError):
        Band(5.0, 1.0)


def test_hysteresis_band_holds_the_previous_verdict():
    band = HysteresisBand(100.0, 800.0, 10.0)
    assert band.classify(900.0) == ABOVE
    assert band.classify(805.0) == ABOVE
    assert band.classify(400.0) == ABOVE
    assert band.classify(80.0) == BELOW
    assert band.last == BELOW


def test_window_keeps_the_most_recent_samples():
    window = Window(3)
    assert window.is_full() is False
    for value in (1.0, 2.0, 3.0, 4.0):
        window.push(value)
    assert window.values() == (2.0, 3.0, 4.0)
    assert window.average() == 3.0
    assert window.span() == 2.0
    assert window.is_full() is True
    assert len(window) == 3
    window.clear()
    assert window.values() == ()
    assert window.average() == 0.0
    assert window.span() == 0.0
    with pytest.raises(ValueError):
        Window(0)


def test_window_evaluator_needs_a_full_window():
    evaluator = WindowEvaluator(Window(3), 12.0, ABOVE_MODE, 3)
    assert evaluator.push(20.0).verdict == INSUFFICIENT
    assert evaluator.push(20.0).verdict == INSUFFICIENT
    result = evaluator.push(20.0)
    assert result.verdict == SUSTAINED
    assert result.samples == 3 and result.required == 3
    assert evaluator.push(3.0).verdict == TRANSIENT
    assert evaluator.window.values() == (20.0, 20.0, 3.0)
    assert evaluator.threshold == 12.0
    assert evaluator.mode == ABOVE_MODE


def test_compare_guards_the_mode():
    assert compare([5.0, 6.0], 4.0, ABOVE_MODE) is True
    assert compare([5.0, 3.0], 4.0, ABOVE_MODE) is False
    assert compare([1.0, 2.0], 4.0, BELOW_MODE) is True
    assert compare([], 4.0, ABOVE_MODE) is False
    with pytest.raises(ValueError):
        compare([1.0], 2.0, "sideways")
    with pytest.raises(ValueError):
        WindowEvaluator(Window(2), 1.0, "sideways", 1)


def test_verdict_history_tracks_watermarks():
    history = VerdictHistory("water.moisture")
    assert history.current() == "unknown"
    history.record("in_band", 1, 1, "reading=6")
    history.record("high", 4, 3, "reading=20")
    assert history.current() == "high"
    assert history.at(0) == "unknown"
    assert history.at(2) == "in_band"
    assert history.changed_since(2) is True
    assert history.subject == "water.moisture"
    assert len(history.points()) == 2
    assert history.to_dict()["current"] == "high"
    history.clear()
    assert history.current() == "unknown"


def test_record_filter_matches_and_describes():
    record_filter = RecordFilter(
        topic="steam.valve.changed",
        key_prefix="steam/",
        min_generation=1,
        kinds=("event",),
    )
    row = {
        "topic": "steam.valve.changed",
        "key": "steam/valve",
        "generation": 2,
        "seq": 5,
        "kind": "event",
    }
    assert record_filter.matches(row) is True
    assert record_filter.matches({**row, "generation": 0}) is False
    assert record_filter.matches({**row, "key": "dry/speed"}) is False
    assert record_filter.apply([row]) == [row]
    described = record_filter.describe()
    assert described["kinds"] == ["event"]


def test_parse_filter_reads_query_parameters():
    parsed = parse_filter(
        {"topic": "broke.handled", "min_seq": "3", "max_seq": "", "kind": "event,tombstone"}
    )
    assert parsed.topic == "broke.handled"
    assert parsed.min_seq == 3
    assert parsed.max_seq is None
    assert parsed.kinds == ("event", "tombstone")


def test_batch_registry_reserves_each_batch_once(journal):
    batches = BatchRegistry(journal)
    batches.reserve("B-1", {"volume": 12.0})
    assert batches.is_reserved("B-1") is True
    assert batches.payload("B-1")["volume"] == 12.0
    with pytest.raises(DuplicateBatchError):
        batches.reserve("B-1", {"volume": 1.0})
    assert batches.reserved_ids() == ("B-1",)
    assert len(batches.entries()) == 1
    batches.release("B-1")
    assert batches.is_reserved("B-1") is False
    with pytest.raises(UnknownBatchError):
        batches.release("B-2")
