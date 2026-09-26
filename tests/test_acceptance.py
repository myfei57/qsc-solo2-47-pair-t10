"""End to end behaviour across the subsystem contracts."""

from paperops.config import Config
from paperops.console.server import ControlServer

from support import WEB_DIR, build, call, ok, refused, run_line


def test_full_line_sequence_runs_in_order(console):
    run_line(console)
    state = ok(console, "GET", "/api/state")
    subsystems = state["subsystems"]
    assert subsystems["press"]["persisted"] is True
    assert subsystems["steam"]["valve_open"] is True
    assert subsystems["dry"]["speed"] == 900
    assert subsystems["glue"]["roll_lifted"] is True
    assert subsystems["glue"]["pump_running"] is False
    assert subsystems["cal"]["nip_closed"] is True
    assert subsystems["reel"]["spool_loaded"] is True
    assert subsystems["reel"]["retracted"] is True


def test_speed_up_before_dewater_is_refused(console):
    response = refused(console, "POST", "/api/dry/speed", {"speed": 900})
    assert response.status == 409
    assert response.body["error"] == "dry.speed needs press/state to be durable first"
    assert call(console, "GET", "/api/journal/keys").body["keys"] == []


def test_steam_valve_before_drain_is_refused(console):
    response = refused(console, "POST", "/api/steam/valve", {"open": True})
    assert response.status == 409
    ok(console, "POST", "/api/steam/drain", {})
    assert ok(console, "POST", "/api/steam/valve", {"open": True})["valve_open"] is True


def test_glue_stop_before_roll_lift_is_refused(console):
    response = refused(console, "POST", "/api/glue/stop", {})
    assert response.status == 409
    ok(console, "POST", "/api/glue/roll", {"lifted": True})
    assert ok(console, "POST", "/api/glue/stop", {})["running"] is False


def test_reel_retract_before_new_spool_is_refused(console):
    ok(console, "POST", "/api/reel/change", {"reason": "full spool"})
    response = refused(console, "POST", "/api/reel/retract", {})
    assert response.status == 409
    assert response.body["error"] == "reel.retract needs reel/spool to be durable first"


def test_broke_latch_holds_until_broke_is_processed(console):
    ok(console, "POST", "/api/broke/trip", {"reason": "web break"})
    response = refused(console, "POST", "/api/broke/reset", {})
    assert response.status == 409
    ok(console, "POST", "/api/broke/process", {"volume": 12, "batch_id": "B-1"})
    assert ok(console, "POST", "/api/broke/reset", {})["latched"] is False
    assert ok(console, "POST", "/api/broke/takeover", {})["next"] == "complete"


def test_restart_restores_every_subsystem(config):
    first = build(config)
    run_line(first.console)

    second = build(config)
    assert second.press.persisted() is True
    assert second.steam.drained() is True
    assert second.steam.valve_open() is True
    assert second.dry.speed() == 900
    assert second.dry.procedure()["next"] == "complete"
    assert second.glue.roll_lifted() is True
    assert second.cal.nip_closed() is True
    assert second.reel.spool_id() == "S-1"
    assert second.reel.retracted() is True
    assert second.audit.sequence > 0
    assert second.journal.watermark > 0


def test_two_runs_of_the_same_sequence_agree(tmp_path):
    digests = []
    for index in range(2):
        config = Config(data_dir=str(tmp_path / f"run{index}"), web_dir=WEB_DIR)
        services = build(config)
        run_line(services.console)
        digests.append(services.journal.view().digest())
    assert digests[0] == digests[1]


def test_uncommitted_work_is_invisible_to_the_rest_of_the_service(services):
    services.journal.open("draft")
    services.journal.append("press/state", {"load": 42.0, "dryness": 45.0}, "draft")
    assert services.journal.read("press/state") is None
    assert ok(services.console, "GET", "/api/journal/pending")["pending"] == ["draft"]
    services.journal.commit("draft")
    assert services.journal.read("press/state") == {"load": 42.0, "dryness": 45.0}


def test_console_server_binds_a_local_port(console):
    server = ControlServer(("127.0.0.1", 0), console)
    try:
        host, port = server.server_address[:2]
        assert host == "127.0.0.1"
        assert port > 0
    finally:
        server.server_close()


def test_page_directory_is_delivered_from_the_configured_path(console):
    response = call(console, "GET", "/operations.html")
    assert response.status == 200
    assert "操作台" in response.to_bytes().decode("utf-8")
