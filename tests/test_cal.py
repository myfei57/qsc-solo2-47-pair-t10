"""Calender nip loading and machine speed."""

from support import ok, refused


def prepare_speed(console) -> None:
    ok(console, "POST", "/api/press/dewater", {"inlet_moisture": 60, "width": 6})
    ok(console, "POST", "/api/press/persist", {"speed": 900})
    ok(console, "POST", "/api/dry/speed", {"speed": 900})
    ok(console, "POST", "/api/cal/speed", {"speed": 900, "target": 900})


def test_nip_closes_once_speed_is_durable(console, services):
    prepare_speed(console)
    assert ok(console, "POST", "/api/cal/nip", {"closed": True, "pressure": 60})["pressure"] == 60.0
    assert services.cal.nip_closed() is True
    assert services.cal.load() == 360.0
    assert ok(console, "POST", "/api/cal/nip", {"closed": False})["nip_closed"] is False
    assert services.cal.nip_closed() is False


def test_nip_needs_a_durable_speed(console):
    response = refused(console, "POST", "/api/cal/nip", {"closed": True, "pressure": 60})
    assert response.status == 409
    assert "dry/speed" in response.body["error"]


def test_nip_waits_for_a_settled_speed(console):
    ok(console, "POST", "/api/press/dewater", {"inlet_moisture": 60, "width": 6})
    ok(console, "POST", "/api/press/persist", {"speed": 900})
    ok(console, "POST", "/api/dry/speed", {"speed": 900})
    ok(console, "POST", "/api/cal/speed", {"speed": 900, "target": 800})
    response = refused(console, "POST", "/api/cal/nip", {"closed": True, "pressure": 60})
    assert response.status == 409
    assert "not settled" in response.body["error"]


def test_cal_model_reports_the_arithmetic(console):
    prepare_speed(console)
    ok(console, "POST", "/api/cal/nip", {"closed": True, "pressure": 60})
    body = ok(console, "GET", "/api/cal/model?width=6&dwell=0.05")
    assert body["nip_load"] == 360.0
    assert body["nip_impulse"] == 3.0
    assert body["speed_difference"] == 0.0
    assert body["settled"] is True
    assert body["nip_verdict"] == "in_band"
