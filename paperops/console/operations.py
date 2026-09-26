"""Write side of the control console."""

from typing import Any

from .http import Request, Response, json_response


def confirmation_issue(console: Any, request: Request) -> Response:
    body = request.body()
    confirmation = console.services.confirmations.issue(
        body["name"],
        body["subject"],
        int(body.get("ttl_ticks", 10)),
    )
    return json_response(confirmation.to_row())


def journal_advance_tick(console: Any, request: Request) -> Response:
    body = request.body()
    tick = console.services.clock.advance(int(body.get("steps", 1)))
    return json_response({"tick": tick})


def journal_maintenance(console: Any, request: Request) -> Response:
    body = request.body()
    console.services.journal.set_read_only(bool(body.get("on", False)))
    return json_response({"read_only": console.services.journal.read_only})


def journal_commit(console: Any, request: Request) -> Response:
    batch_id = request.body()["batch_id"]
    watermark = console.services.journal.commit(batch_id)
    return json_response({"batch_id": batch_id, "watermark": watermark})


def journal_discard(console: Any, request: Request) -> Response:
    batch_id = request.body()["batch_id"]
    dropped = console.services.journal.discard(batch_id)
    return json_response({"batch_id": batch_id, "dropped": dropped})


def journal_rollback(console: Any, request: Request) -> Response:
    body = request.body()
    batch_id = body["batch_id"]
    restored = console.services.journal.rollback(
        batch_id, body.get("reason", "operator rollback")
    )
    return json_response({"batch_id": batch_id, "keys_restored": restored})


def state_snapshot(console: Any, request: Request) -> Response:
    return json_response(console.services.state.snapshot())


def audit_clear(console: Any, request: Request) -> Response:
    return json_response({"cleared": console.services.audit.clear()})


def batch_release(console: Any, request: Request) -> Response:
    """Forget a recorded process batch so its identifier can be issued again."""
    batch_id = request.body()["batch_id"]
    console.services.batches.release(batch_id)
    return json_response(
        {
            "released": batch_id,
            "reserved": list(console.services.batches.reserved_ids()),
        }
    )


def press_load(console: Any, request: Request) -> Response:
    console.services.press.set_load(request.body()["load"])
    return json_response({"load": console.services.press.load()})


def press_dewater(console: Any, request: Request) -> Response:
    body = request.body()
    row = console.services.press.dewater(body["inlet_moisture"], body.get("width", 6.0))
    return json_response(row)


def press_persist(console: Any, request: Request) -> Response:
    speed = request.body().get("speed", console.services.dry.speed())
    tick = console.services.press.persist(float(speed))
    return json_response({"persisted": True, "tick": tick})


def press_gain(console: Any, request: Request) -> Response:
    body = request.body()
    return json_response(
        console.services.press.recalibrate_gain(body["gain"], body["confirmation_id"])
    )


def dry_begin(console: Any, request: Request) -> Response:
    return json_response(console.services.dry.begin())


def dry_drain(console: Any, request: Request) -> Response:
    return json_response(console.services.dry.drain_done())


def dry_admit(console: Any, request: Request) -> Response:
    return json_response(console.services.dry.admit_steam(console.services.steam))


def dry_warm(console: Any, request: Request) -> Response:
    return json_response(console.services.dry.warm_up())


def dry_run(console: Any, request: Request) -> Response:
    return json_response(console.services.dry.dry())


def dry_heat(console: Any, request: Request) -> Response:
    return json_response(console.services.dry.heat(request.body()["target"]))


def dry_speed(console: Any, request: Request) -> Response:
    target = request.body()["speed"]
    return json_response(console.services.dry.speed_up(console.services.press, target))


def dry_curve(console: Any, request: Request) -> Response:
    body = request.body()
    row = console.services.dry.recalibrate_curve(
        body["slope"],
        body["base"],
        body["confirmation_id"],
    )
    return json_response(row)


def steam_drain(console: Any, request: Request) -> Response:
    return json_response({"drained": True, "tick": console.services.steam.drain()})


def steam_valve(console: Any, request: Request) -> Response:
    body = request.body()
    if body.get("open", True):
        return json_response(console.services.steam.open_valve())
    return json_response(console.services.steam.close_valve())


def steam_stop(console: Any, request: Request) -> Response:
    """Orderly stop: the spool transfer has to be finished before steam is shut."""
    return json_response(console.services.steam.close_for_stop(console.services.reel))


def steam_calibrate(console: Any, request: Request) -> Response:
    body = request.body()
    return json_response(
        console.services.steam.calibrate(body["pressure"], body["confirmation_id"])
    )


def steam_gauge(console: Any, request: Request) -> Response:
    return json_response({"generation": console.services.steam.replace_gauge()})


def glue_roll(console: Any, request: Request) -> Response:
    body = request.body()
    if body.get("lifted", True):
        return json_response(console.services.glue.lift_roll())
    return json_response(console.services.glue.lower_roll())


def glue_pump(console: Any, request: Request) -> Response:
    body = request.body()
    if body.get("running", False):
        return json_response(console.services.glue.start_pump())
    return json_response(console.services.glue.stop_pump())


def glue_stop(console: Any, request: Request) -> Response:
    """Stop the glue pump; the sizing roll has to be lifted first."""
    return json_response(console.services.glue.stop_pump())


def glue_alarm(console: Any, request: Request) -> Response:
    body = request.body()
    if body.get("on", True):
        return json_response(console.services.glue.set_alarm())
    return json_response(console.services.glue.clear_alarm())


def glue_concentration(console: Any, request: Request) -> Response:
    body = request.body()
    return json_response(
        console.services.glue.set_concentration(body["value"], body["confirmation_id"])
    )


def cal_speed(console: Any, request: Request) -> Response:
    body = request.body()
    return json_response(console.services.cal.set_speed(body["speed"], body["target"]))


def cal_nip(console: Any, request: Request) -> Response:
    body = request.body()
    if body.get("closed", True):
        return json_response(
            console.services.cal.close_nip(console.services.dry, body["pressure"])
        )
    return json_response(console.services.cal.open_nip())


def reel_change(console: Any, request: Request) -> Response:
    return json_response(console.services.reel.begin_change(request.body().get("reason", "full spool")))


def reel_spool(console: Any, request: Request) -> Response:
    body = request.body()
    return json_response(
        console.services.reel.new_spool(body["spool_id"], console.services.cal)
    )


def reel_retract(console: Any, request: Request) -> Response:
    return json_response(console.services.reel.retract_old())


def reel_bite(console: Any, request: Request) -> Response:
    return json_response(console.services.reel.bite())


def reel_break(console: Any, request: Request) -> Response:
    body = request.body()
    return json_response(
        console.services.reel.trigger_break(console.services.broke, body.get("reason", "web break"))
    )


def broke_trip(console: Any, request: Request) -> Response:
    return json_response(console.services.broke.trip(request.body().get("reason", "web break")))


def broke_process(console: Any, request: Request) -> Response:
    body = request.body()
    return json_response(console.services.broke.process(body["volume"], body["batch_id"]))


def broke_reset(console: Any, request: Request) -> Response:
    return json_response(console.services.broke.reset_latch())


def broke_takeover(console: Any, request: Request) -> Response:
    return json_response(console.services.broke.take_over())


def water_map(console: Any, request: Request) -> Response:
    body = request.body()
    sensors = {str(name): float(position) for name, position in body["sensors"].items()}
    return json_response(console.services.water.rebuild_map(sensors, body["confirmation_id"]))


def water_scanner(console: Any, request: Request) -> Response:
    return json_response({"generation": console.services.water.replace_scanner()})


def water_sample(console: Any, request: Request) -> Response:
    body = request.body()
    return json_response(console.services.water.add_sample(body["name"], body["moisture"]))


def water_reading(console: Any, request: Request) -> Response:
    body = request.body()
    return json_response(
        console.services.water.add_reading(body["name"], body["position"], body["moisture"])
    )


def water_profile(console: Any, request: Request) -> Response:
    return json_response(console.services.water.record_profile())
