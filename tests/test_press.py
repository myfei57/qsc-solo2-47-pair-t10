"""Press section dewatering and its durable record."""

import pytest

from paperops.errors import OutOfRangeError
from paperops.store import Journal

from support import build, issue_confirmation, ok


def test_dewater_records_the_dryness(console, services):
    ok(console, "POST", "/api/press/load", {"load": 45})
    row = ok(console, "POST", "/api/press/dewater", {"inlet_moisture": 60, "width": 6})
    assert row["load"] == 270.0
    assert round(row["outlet_moisture"], 2) == 45.4
    assert round(row["removed"], 2) == 14.6
    assert services.press.dryness() == row["outlet_moisture"]
    assert services.press.readings() == (row["outlet_moisture"],)
    assert round(services.press.average_dryness(), 2) == 45.4


def test_persist_releases_the_drive(console, services):
    ok(console, "POST", "/api/press/dewater", {"inlet_moisture": 60, "width": 6})
    tick = ok(console, "POST", "/api/press/persist", {"speed": 900})["tick"]
    assert services.press.persisted() is True
    assert services.press.view().persisted_tick == tick
    assert ok(console, "POST", "/api/dry/speed", {"speed": 900})["speed"] == 900


def test_press_model_reports_the_arithmetic(console, services):
    ok(console, "POST", "/api/press/load", {"load": 45})
    body = ok(console, "GET", "/api/press/model?width=6&inlet=60")
    assert body["nip_load"] == 270.0
    assert round(body["dryness"], 2) == 45.4
    assert round(body["removed"], 2) == 14.6
    assert body["load_factor"] == 1.5
    assert body["overload"] is True
    assert round(body["extraction"], 2) == 9.45
    assert body["spread"] == 0.0


def test_press_band_and_negative_guards(console):
    from support import refused

    assert ok(console, "GET", "/api/press/model?inlet=60")["band"] == 60.0
    assert refused(console, "GET", "/api/press/model?inlet=200").status == 422


def test_gain_change_needs_a_confirmation(console, services):
    body = ok(
        console,
        "POST",
        "/api/press/gain",
        {"gain": 0.03, "confirmation_id": issue_confirmation(console, "press.dewater", "press")},
    )
    assert body["generation"] == 1
    assert services.press.view().generation == 1
    # a wrong-subject confirmation is refused
    from support import refused

    response = refused(
        console,
        "POST",
        "/api/press/gain",
        {"gain": 0.03, "confirmation_id": issue_confirmation(console, "press.dewater", "dry")},
    )
    assert response.status == 422


def test_persisted_press_state_survives_a_restart(config):
    first = build(config)
    ok(first.console, "POST", "/api/press/load", {"load": 45})
    ok(first.console, "POST", "/api/press/dewater", {"inlet_moisture": 60, "width": 6})
    ok(first.console, "POST", "/api/press/persist", {"speed": 900})

    second = build(config)
    assert second.press.persisted() is True
    assert second.press.load() == 45.0
    assert round(second.press.dryness(), 2) == 45.4


def test_negative_load_is_refused(services):
    with pytest.raises(ValueError):
        services.press.set_load(-1)
    with pytest.raises(OutOfRangeError):
        services.press.verify_band(200.0, "inlet moisture")


def test_pure_helpers_match_calculation():
    from paperops.clock import IdSequence, LogicalClock
    from paperops.event import EventBus
    from paperops.press.service import PressService
    from paperops.version import Confirmations, Generations

    journal = Journal()
    clock = LogicalClock()
    generations = Generations(journal)
    press = PressService(
        journal,
        EventBus(),
        clock,
        generations,
        Confirmations(journal, clock, IdSequence("cfm"), generations),
    )
    press.set_load(45)
    assert press.nip_load(6) == 270.0
    assert press.load_factor(180) == 1.5
    assert press.overload(180) is True
    assert round(press.water_removed(60, 45.4), 2) == 14.6
    assert press.spread([1.0, 2.0, 4.0]) == 3.0
    assert press.reject_negative(5.0, "volume") == 5.0
