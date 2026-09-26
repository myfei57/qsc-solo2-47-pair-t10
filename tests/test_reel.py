"""Reel spool transfer order and geometry."""

from support import ok, refused


def prepare_nip(console) -> None:
    ok(console, "POST", "/api/press/dewater", {"inlet_moisture": 60, "width": 6})
    ok(console, "POST", "/api/press/persist", {"speed": 900})
    ok(console, "POST", "/api/dry/speed", {"speed": 900})
    ok(console, "POST", "/api/cal/speed", {"speed": 900, "target": 900})
    ok(console, "POST", "/api/cal/nip", {"closed": True, "pressure": 60})


def test_transfer_walks_through_every_stage(console, services):
    prepare_nip(console)
    ok(console, "POST", "/api/reel/change", {"reason": "full spool"})
    assert services.reel.procedure()["next"] == "new_spool"
    ok(console, "POST", "/api/reel/spool", {"spool_id": "S-9"})
    assert services.reel.spool_loaded() is True
    ok(console, "POST", "/api/reel/retract", {})
    assert services.reel.retracted() is True
    ok(console, "POST", "/api/reel/bite", {})
    assert services.reel.procedure()["next"] == "complete"


def test_new_spool_needs_a_loaded_nip(console, services):
    ok(console, "POST", "/api/reel/change", {"reason": "full spool"})
    response = refused(console, "POST", "/api/reel/spool", {"spool_id": "S-9"})
    assert response.status == 409
    assert "calender nip" in response.body["error"]


def test_retract_needs_the_new_spool(console):
    prepare_nip(console)
    ok(console, "POST", "/api/reel/change", {"reason": "full spool"})
    response = refused(console, "POST", "/api/reel/retract", {})
    assert response.status == 409


def test_reel_geometry(console):
    body = ok(console, "GET", "/api/reel/geometry?core=150&thickness=0.08&wraps=4000")
    assert body["diameter"] == 790.0
    assert body["remaining"] == 4000.0
    assert body["length"] > 0
    assert body["turn_up"] == "ready"


def test_reel_can_hand_a_break_to_broke(console, services):
    ok(console, "POST", "/api/reel/break", {"reason": "snap"})
    assert services.broke.latched() is True
    assert services.broke.procedure()["completed"] == ["break"]


def test_spool_transfer_survives_a_restart(config):
    from support import build

    first = build(config)
    prepare_nip(first.console)
    ok(first.console, "POST", "/api/reel/change", {"reason": "full spool"})
    ok(first.console, "POST", "/api/reel/spool", {"spool_id": "S-42"})
    ok(first.console, "POST", "/api/reel/retract", {})
    second = build(config)
    assert second.reel.spool_id() == "S-42"
    assert second.reel.spool_loaded() is True
    assert second.reel.retracted() is True
