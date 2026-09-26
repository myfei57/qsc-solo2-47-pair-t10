"""Condensate order, admission valve and the pressure baseline."""

import pytest

from paperops.errors import StaleArtifactError

from support import build, issue_confirmation, ok, refused


def test_valve_needs_a_durable_drain(console, services):
    response = refused(console, "POST", "/api/steam/valve", {"open": True})
    assert response.status == 409
    assert "steam/drain" in response.body["error"]
    ok(console, "POST", "/api/steam/drain", {})
    assert services.steam.drained() is True
    assert ok(console, "POST", "/api/steam/valve", {"open": True})["valve_open"] is True
    assert ok(console, "POST", "/api/steam/valve", {"open": False})["valve_open"] is False


def test_baseline_calibration_binds_a_confirmation(console, services):
    body = ok(
        console,
        "POST",
        "/api/steam/calibrate",
        {"pressure": 6.0, "confirmation_id": issue_confirmation(console, "steam.baseline", "steam")},
    )
    assert body["baseline"] == 6.0
    assert services.steam.generation() == 1
    assert ok(console, "GET", "/api/steam/pressure?reading=6.1")["verdict"] == "in_band"
    assert round(ok(console, "GET", "/api/steam/pressure?reading=7.0")["offset"], 2) == 1.0


def test_replacing_the_gauge_invalidates_the_baseline(console, services):
    ok(
        console,
        "POST",
        "/api/steam/calibrate",
        {"pressure": 6.0, "confirmation_id": issue_confirmation(console, "steam.baseline", "steam")},
    )
    ok(console, "POST", "/api/steam/gauge", {})
    assert services.generations.current("steam.baseline") == 2
    with pytest.raises(StaleArtifactError):
        services.steam.require_fresh_baseline()
    assert refused(console, "GET", "/api/steam/pressure?reading=6.1").status == 409


def test_pressure_verdict_needs_a_calibration(console):
    assert refused(console, "GET", "/api/steam/pressure?reading=6.0").status == 409


def test_steam_model_arithmetic(console):
    body = ok(console, "GET", "/api/steam/model?supply=8&header=6&pressure=6&flow=10&dryness=0.95")
    assert body["drop"] == 2.0
    assert round(body["saturation"], 2) == 103.72
    assert round(body["condensate"], 2) == 0.5
    assert body["window"] == "in_band"


def test_drain_survives_a_restart(config):
    first = build(config)
    ok(first.console, "POST", "/api/steam/drain", {})
    ok(first.console, "POST", "/api/steam/valve", {"open": True})
    second = build(config)
    assert second.steam.drained() is True
    assert second.steam.valve_open() is True


def test_orderly_stop_needs_a_finished_spool_transfer(console, services):
    ok(console, "POST", "/api/steam/drain", {})
    ok(console, "POST", "/api/steam/valve", {"open": True})
    ok(console, "POST", "/api/reel/change", {"reason": "full spool"})
    response = refused(console, "POST", "/api/steam/stop", {})
    assert response.status == 409
    assert "not finished" in response.body["error"]

    ok(console, "POST", "/api/press/dewater", {"inlet_moisture": 60, "width": 6})
    ok(console, "POST", "/api/press/persist", {"speed": 900})
    ok(console, "POST", "/api/dry/speed", {"speed": 900})
    ok(console, "POST", "/api/cal/speed", {"speed": 900, "target": 900})
    ok(console, "POST", "/api/cal/nip", {"closed": True, "pressure": 60})
    ok(console, "POST", "/api/reel/spool", {"spool_id": "S-1"})
    ok(console, "POST", "/api/reel/retract", {})
    ok(console, "POST", "/api/reel/bite", {})

    body = ok(console, "POST", "/api/steam/stop", {})
    assert body["valve_open"] is False
    assert body["order"] == "reel-complete"
    assert services.steam.valve_open() is False
