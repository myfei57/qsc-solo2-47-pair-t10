"""Sensor mapping, samples and the cross direction profile."""

import pytest

from paperops.errors import UnknownSensorError

from support import build, issue_confirmation, ok, refused


def test_default_map_and_samples(console, services):
    assert services.water.map_sensors() == {"front": 0.4, "middle": 3.1, "back": 5.8}
    ok(console, "POST", "/api/water/sample", {"name": "front", "moisture": 6.0})
    assert services.water.values() == (6.0,)
    assert services.water.average() == 6.0
    assert services.water.span() == 0.0


def test_unknown_sensor_is_refused(console, services):
    response = refused(console, "POST", "/api/water/sample", {"name": "edge", "moisture": 6.0})
    assert response.status == 404
    with pytest.raises(UnknownSensorError):
        services.water.add_sample("edge", 6.0)


def test_rebuild_map_binds_a_confirmation(console, services):
    body = ok(
        console,
        "POST",
        "/api/water/map",
        {
            "sensors": {"front": 0.5, "middle": 3.0, "back": 5.5},
            "confirmation_id": issue_confirmation(console, "water.map", "water"),
        },
    )
    assert body["generation"] == 1
    assert services.water.map_sensors() == {"front": 0.5, "middle": 3.0, "back": 5.5}
    assert services.water.generation() == 1


def test_profile_follows_the_samples(console, services):
    ok(console, "POST", "/api/water/reading", {"name": "left", "position": 1.0, "moisture": 5.0})
    ok(console, "POST", "/api/water/reading", {"name": "right", "position": 5.0, "moisture": 9.0})
    profile = ok(console, "GET", "/api/water/profile")
    assert profile["profile"] == [
        {"position": 1.0, "moisture": 5.0},
        {"position": 5.0, "moisture": 9.0},
    ]
    assert profile["average"] == 7.0
    assert profile["span"] == 4.0
    assert profile["at"] == 7.0


def test_profile_is_recorded_as_a_curve(console, services):
    ok(console, "POST", "/api/water/reading", {"name": "mid", "position": 3.0, "moisture": 7.0})
    body = ok(console, "POST", "/api/water/profile", {})
    assert body["average"] == 7.0
    assert len(body["points"]) == 1


def test_moisture_verdicts_and_window(console, services):
    assert ok(console, "GET", "/api/water/verdict?reading=6")["verdict"] == "in_band"
    assert ok(console, "GET", "/api/water/verdict?reading=1")["verdict"] == "low"
    assert ok(console, "GET", "/api/water/verdict?reading=20")["verdict"] == "high"
    for _ in range(3):
        verdict = services.water.sustained_dry(13.0)
    assert verdict.verdict == "sustained"


def test_scanner_change_moves_the_generation(console, services):
    ok(console, "POST", "/api/water/scanner", {})
    assert services.generations.current("water.map") == 1
    assert refused(console, "GET", "/api/water/model?reading=6&volume=-1").status == 422


def test_map_and_samples_survive_a_restart(config):
    first = build(config)
    ok(
        first.console,
        "POST",
        "/api/water/map",
        {
            "sensors": {"front": 0.2, "middle": 3.0, "back": 5.6},
            "confirmation_id": issue_confirmation(first.console, "water.map", "water"),
        },
    )
    ok(first.console, "POST", "/api/water/sample", {"name": "middle", "moisture": 7.5})
    second = build(config)
    assert second.water.map_sensors() == {"front": 0.2, "middle": 3.0, "back": 5.6}
    assert second.water.values() == (7.5,)
