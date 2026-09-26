"""Broke handling procedure and its latch."""

from support import build, ok, refused


def test_break_latches_and_opens_the_procedure(console, services):
    body = ok(console, "POST", "/api/broke/trip", {"reason": "web break"})
    assert body["latched"] is True
    assert services.broke.latched() is True
    assert services.broke.procedure()["next"] == "process"


def test_latch_reset_needs_processed_broke(console, services):
    ok(console, "POST", "/api/broke/trip", {"reason": "web break"})
    response = refused(console, "POST", "/api/broke/reset", {})
    assert response.status == 409
    ok(console, "POST", "/api/broke/process", {"volume": 12, "batch_id": "B-1"})
    assert services.broke.handled() is True
    assert ok(console, "POST", "/api/broke/reset", {})["latched"] is False
    assert services.broke.latched() is False


def test_process_needs_a_registered_break(console):
    response = refused(console, "POST", "/api/broke/process", {"volume": 1, "batch_id": "B-9"})
    assert response.status == 409


def test_repeated_batch_is_refused(console):
    ok(console, "POST", "/api/broke/trip", {"reason": "web break"})
    ok(console, "POST", "/api/broke/process", {"volume": 12, "batch_id": "B-1"})
    response = refused(console, "POST", "/api/broke/process", {"volume": 3, "batch_id": "B-1"})
    assert response.status == 409


def test_take_over_needs_a_clear_latch(console, services):
    ok(console, "POST", "/api/broke/trip", {"reason": "web break"})
    response = refused(console, "POST", "/api/broke/takeover", {})
    assert response.status == 409
    ok(console, "POST", "/api/broke/process", {"volume": 12, "batch_id": "B-1"})
    ok(console, "POST", "/api/broke/reset", {})
    assert ok(console, "POST", "/api/broke/takeover", {})["next"] == "complete"


def test_broke_model_arithmetic(console):
    body = ok(console, "GET", "/api/broke/model?volume=12&seconds=60&recovered=9&generated=12&consistency=3")
    assert body["rate"] == 0.2
    assert body["recovery"] == 0.75
    assert round(body["reprocessed"], 2) == 0.36
    assert body["verdict"] == "held"


def test_latch_position_survives_a_restart(config):
    first = build(config)
    ok(first.console, "POST", "/api/broke/trip", {"reason": "web break"})
    second = build(config)
    assert second.broke.latched() is True
    assert second.broke.batches() == ()

    ok(second.console, "POST", "/api/broke/process", {"volume": 12, "batch_id": "B-1"})
    ok(second.console, "POST", "/api/broke/reset", {})
    third = build(config)
    assert third.broke.latched() is False
    assert third.broke.handled() is True
    assert third.broke.batch_total() == 12.0
