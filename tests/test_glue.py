"""Sizing roll, glue pump and the concentration alarm latch."""

import pytest

from paperops.errors import LatchSetError

from support import issue_confirmation, ok, refused


def test_pump_stop_needs_the_roll_lifted(console, services):
    response = refused(console, "POST", "/api/glue/stop", {})
    assert response.status == 409
    ok(console, "POST", "/api/glue/roll", {"lifted": True})
    assert services.glue.roll_lifted() is True
    assert ok(console, "POST", "/api/glue/stop", {})["running"] is False
    assert ok(console, "POST", "/api/glue/pump", {"running": True})["running"] is True
    assert ok(console, "POST", "/api/glue/roll", {"lifted": False})["roll_lifted"] is False


def test_alarm_latch_needs_the_pump_stopped(console, services):
    ok(console, "POST", "/api/glue/roll", {"lifted": True})
    ok(console, "POST", "/api/glue/pump", {"running": True})
    with pytest.raises(LatchSetError):
        services.glue.set_alarm()
    ok(console, "POST", "/api/glue/stop", {})
    assert ok(console, "POST", "/api/glue/alarm", {"on": True})["alarm"] is True
    assert services.glue.alarm() is True
    assert ok(console, "POST", "/api/glue/alarm", {"on": False})["alarm"] is False


def test_concentration_band_and_cache(console, services):
    body = ok(
        console,
        "POST",
        "/api/glue/concentration",
        {"value": 8.0, "confirmation_id": issue_confirmation(console, "glue.concentration", "glue")},
    )
    assert body["generation"] == 1
    assert services.glue.view().verdict == "in_band"
    assert ok(console, "GET", "/api/glue/model?reading=2")["verdict"] == "lean"
    assert ok(console, "GET", "/api/glue/model?reading=20")["verdict"] == "rich"
    assert ok(console, "GET", "/api/glue/model?reading=20")["cached"] == "rich"
    assert ok(console, "GET", "/api/glue/model?reading=20")["alarm_required"] is True


def test_glue_model_arithmetic(console):
    body = ok(console, "GET", "/api/glue/model?roll=30&stock=900&flow=4&width=6&speed=900&concentration=8&water=2")
    assert round(body["pick_up"], 4) == 0.0333
    assert round(body["dose"], 6) == 0.000741
    assert body["diluted"] == 0.8


def test_glue_state_survives_a_restart(config):
    from support import build

    first = build(config)
    ok(first.console, "POST", "/api/glue/roll", {"lifted": True})
    ok(first.console, "POST", "/api/glue/stop", {})
    ok(first.console, "POST", "/api/glue/alarm", {"on": True})
    second = build(config)
    assert second.glue.roll_lifted() is True
    assert second.glue.pump_running() is False
    assert second.glue.alarm() is True
