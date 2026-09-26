"""Dryer procedure, speed release and the drying curve."""

from support import issue_confirmation, ok, refused


def test_procedure_walks_through_every_stage(console, services):
    ok(console, "POST", "/api/dry/begin", {})
    assert services.dry.procedure()["next"] == "drain"
    ok(console, "POST", "/api/steam/drain", {})
    ok(console, "POST", "/api/dry/drain", {})
    assert services.dry.procedure()["next"] == "steam"
    ok(console, "POST", "/api/dry/admit", {})
    ok(console, "POST", "/api/dry/warm", {})
    ok(console, "POST", "/api/dry/run", {})
    assert services.dry.procedure()["next"] == "complete"
    assert services.dry.valve_open() is True


def test_dry_cannot_close_a_later_stage_first(console, services):
    ok(console, "POST", "/api/dry/begin", {})
    response = refused(console, "POST", "/api/dry/run", {})
    assert response.status == 409


def test_admit_steam_needs_a_drained_header(console, services):
    ok(console, "POST", "/api/dry/begin", {})
    ok(console, "POST", "/api/dry/drain", {})
    response = refused(console, "POST", "/api/dry/admit", {})
    assert response.status == 409
    assert "condensate is not drained" in response.body["error"]


def test_heat_needs_the_valve_record(console, services):
    ok(console, "POST", "/api/dry/begin", {})
    ok(console, "POST", "/api/dry/drain", {})
    ok(console, "POST", "/api/steam/drain", {})
    ok(console, "POST", "/api/dry/admit", {})
    response = refused(console, "POST", "/api/dry/heat", {"target": 120})
    assert response.status == 409
    ok(console, "POST", "/api/steam/valve", {"open": True})
    assert ok(console, "POST", "/api/dry/heat", {"target": 120})["temperature"] == 120.0


def test_speed_up_needs_the_press_record(console, services):
    response = refused(console, "POST", "/api/dry/speed", {"speed": 850})
    assert response.status == 409
    ok(console, "POST", "/api/press/dewater", {"inlet_moisture": 60, "width": 6})
    ok(console, "POST", "/api/press/persist", {"speed": 850})
    assert ok(console, "POST", "/api/dry/speed", {"speed": 850})["speed"] == 850
    assert services.dry.speed() == 850


def test_drying_curve_needs_a_confirmation(console, services):
    body = ok(
        console,
        "POST",
        "/api/dry/curve",
        {"slope": 1.4, "base": 0.3, "confirmation_id": issue_confirmation(console, "dry.curve", "dry")},
    )
    assert body["generation"] == 1
    assert services.dry.curve()["slope"] == 1.4


def test_dry_model_arithmetic(console):
    body = ok(console, "GET", "/api/dry/model?temperature=100&steam=2&load=10")
    assert body["evaporation"] == 100.0
    assert round(body["heat_duty"], 2) == 4.52
    assert body["time_to_dry"] == 0.1
    assert body["profile_difference"] == 1.0
    assert body["curve"]["slope"] == 1.0


def test_procedure_state_survives_a_restart(config):
    from support import build

    first = build(config)
    ok(first.console, "POST", "/api/steam/drain", {})
    ok(first.console, "POST", "/api/steam/valve", {"open": True})
    ok(first.console, "POST", "/api/dry/begin", {})
    ok(first.console, "POST", "/api/dry/drain", {})
    ok(first.console, "POST", "/api/dry/admit", {})
    second = build(config)
    assert second.dry.procedure()["completed"] == ["drain", "steam"]
    assert second.dry.valve_open() is True
