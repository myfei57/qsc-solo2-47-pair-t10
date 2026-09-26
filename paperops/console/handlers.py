"""Read side of the control console."""

from typing import Any

from ..errors import StaleArtifactError
from ..verdict import parse_filter
from .http import Request, Response, json_response
from .pages import read_page


def health(console: Any, request: Request) -> Response:
    journal = console.services.journal
    return json_response(
        {
            "status": "ok",
            "service": "control",
            "data_dir": journal.directory or "",
            "watermark": journal.watermark,
            "committed_keys": len(journal.keys()),
            "tick": console.services.clock.tick,
        }
    )


def state(console: Any, request: Request) -> Response:
    return json_response(console.services.state.view().to_dict())


def counters(console: Any, request: Request) -> Response:
    return json_response(console.services.state.counters())


def routes(console: Any, request: Request) -> Response:
    return json_response({"routes": [list(route) for route in console.routes()]})


def histories(console: Any, request: Request) -> Response:
    return json_response({"subjects": list(console.services.state.histories())})


def snapshot_status(console: Any, request: Request) -> Response:
    ref = console.services.state.require_snapshot(request.integer("max_age", 100))
    return json_response(ref.to_row())


def artifacts_status(console: Any, request: Request) -> Response:
    artifacts = console.services.artifacts
    generations = console.services.generations
    max_age = request.integer("max_age", 100)
    ref = artifacts.get("snapshot", "control.snapshot")
    if ref is None:
        return json_response({"snapshot": None, "age": None, "stale": True})
    try:
        age = artifacts.age("snapshot", "control.snapshot")
    except StaleArtifactError as error:
        return json_response({"snapshot": ref.to_row(), "age": None, "stale": True, "detail": str(error)})
    return json_response(
        {
            "snapshot": ref.to_row(),
            "age": age,
            "stale": artifacts.stale("snapshot", "control.snapshot", max_age, generations),
        }
    )


def verdict_history(console: Any, request: Request) -> Response:
    subject = request.param("subject", "water.moisture") or "water.moisture"
    history = console.services.state.history(subject)
    if history is None:
        return json_response(console.services.state.verdict_history(subject))
    body = history.to_dict()
    since = request.param("since")
    if since is not None:
        body["changed_since"] = history.changed_since(int(since))
    return json_response(body)


def confirmations(console: Any, request: Request) -> Response:
    outstanding = console.services.confirmations.outstanding()
    return json_response(
        {
            "count": len(outstanding),
            "confirmations": [confirmation.to_row() for confirmation in outstanding],
        }
    )


def batches(console: Any, request: Request) -> Response:
    registry = console.services.batches
    return json_response(
        {
            "reserved": list(registry.reserved_ids()),
            "entries": [dict(entry) for entry in registry.entries()],
        }
    )


def journal_keys(console: Any, request: Request) -> Response:
    prefix = request.param("prefix", "") or ""
    return json_response({"prefix": prefix, "keys": list(console.services.journal.keys(prefix))})


def journal_entries(console: Any, request: Request) -> Response:
    journal = console.services.journal
    record_filter = parse_filter(request.query)
    rows = [
        {**entry.as_filter_row(), "value": entry.value, "reason": entry.reason}
        for entry in journal.entries()
    ]
    kept = record_filter.apply(rows)
    return json_response(
        {
            "filter": record_filter.describe(),
            "count": len(kept),
            "entries": kept,
            "watermark": journal.watermark,
        }
    )


def journal_pending(console: Any, request: Request) -> Response:
    journal = console.services.journal
    return json_response(
        {
            "watermark": journal.watermark,
            "pending": list(journal.pending_batches()),
            "aborted": list(journal.aborted_batches()),
        }
    )


def journal_view(console: Any, request: Request) -> Response:
    journal = console.services.journal
    watermark = request.param("watermark")
    limit = journal.watermark if watermark is None else int(watermark)
    view = journal.view(limit)
    return json_response(
        {
            "watermark": view.watermark,
            "rows": view.rows(),
            "digest": view.digest(),
        }
    )


def journal_stats(console: Any, request: Request) -> Response:
    journal = console.services.journal
    key = request.param("key", "") or ""
    frozen = journal.snapshot()
    return json_response(
        {
            "key": key,
            "present": journal.has(key),
            "value": journal.read(key),
            "required": journal.require(key) if journal.has(key) else None,
            "generation": journal.generation_of(key),
            "committed_count": journal.committed_count,
            "history": [entry.to_row() for entry in journal.history(key)] if key else [],
            "snapshot": frozen.to_dict(),
        }
    )


def audit(console: Any, request: Request) -> Response:
    record_filter = parse_filter(request.query)
    records = console.services.audit.query(record_filter, request.integer("limit", 0))
    return json_response(
        {
            "filter": record_filter.describe(),
            "count": len(records),
            "records": [record.to_row() for record in records],
        }
    )


def audit_summary(console: Any, request: Request) -> Response:
    service = console.services.audit
    summary = service.summary()
    summary["sequence"] = service.sequence
    topic = request.param("topic")
    if topic:
        summary["topic_count"] = service.count(topic)
        summary["topic_records"] = [record.to_row() for record in service.by_topic(topic)]
    news = request.integer("news", 0)
    if news:
        summary["news"] = [record.to_row() for record in service.news(news)]
    return json_response(summary)


def press_state(console: Any, request: Request) -> Response:
    return json_response(console.services.press.view().to_dict())


def press_model(console: Any, request: Request) -> Response:
    press = console.services.press
    width = request.number("width", 6.0)
    inlet = request.number("inlet", 60.0)
    return json_response(
        {
            "nip_load": press.nip_load(width),
            "dryness": press.dryness_for(inlet),
            "removed": press.water_removed(inlet, press.dryness_for(inlet)),
            "load_factor": press.load_factor(180.0),
            "overload": press.overload(180.0),
            "extraction": press.extraction(3.5),
            "spread": press.spread(list(press.readings())),
            "average_dryness": press.average_dryness(),
            "band": press.verify_band(inlet, "inlet moisture"),
            "rejected": press.reject_negative(request.number("volume", 0.0), "volume"),
            "history": press.history().to_dict(),
        }
    )


def dry_state(console: Any, request: Request) -> Response:
    return json_response(console.services.dry.view().to_dict())


def dry_procedure(console: Any, request: Request) -> Response:
    return json_response(console.services.dry.procedure())


def dry_model(console: Any, request: Request) -> Response:
    dry = console.services.dry
    temperature = request.number("temperature", dry.temperature())
    return json_response(
        {
            "evaporation": dry.evaporation(temperature),
            "heat_duty": dry.heat_duty(request.number("steam", 1.0)),
            "time_to_dry": dry.time_to_dry(request.number("load", 10.0), temperature),
            "profile_difference": dry.profile_difference(
                request.number("edges", 7.0), request.number("center", 6.0)
            ),
            "temperature_rise": dry.temperature_rise(request.number("target", 120.0)),
            "steady": dry.steady(request.number("target", 120.0)),
            "valve_open": dry.valve_open(),
            "curve": dry.curve(),
        }
    )


def steam_state(console: Any, request: Request) -> Response:
    return json_response(console.services.steam.view().to_dict())


def steam_pressure(console: Any, request: Request) -> Response:
    steam = console.services.steam
    reading = request.number("reading", steam.view().baseline)
    return json_response(
        {
            "verdict": steam.pressure_of(reading),
            "offset": steam.offset_of(reading),
            "baseline": steam.view().baseline,
            "generation": steam.generation(),
            "history": steam.history().to_dict(),
        }
    )


def steam_model(console: Any, request: Request) -> Response:
    steam = console.services.steam
    return json_response(
        {
            "drop": steam.pressure_drop(request.number("supply", 8.0), request.number("header", 6.0)),
            "saturation": steam.saturation_temperature(request.number("pressure", 6.0)),
            "condensate": steam.condensate_load(
                request.number("flow", 10.0), request.number("dryness", 0.95)
            ),
            "band": steam.verify_band(request.number("pressure", 6.0), "steam pressure"),
            "window": steam.window_verdict(request.number("offset", 0.0), request.number("threshold", 0.15)),
            "drained": steam.drained(),
            "valve_open": steam.valve_open(),
        }
    )


def glue_state(console: Any, request: Request) -> Response:
    return json_response(console.services.glue.view().to_dict())


def glue_model(console: Any, request: Request) -> Response:
    glue = console.services.glue
    reading = request.number("reading", glue.concentration())
    return json_response(
        {
            "verdict": glue.verdict_of(reading),
            "cached": glue.cached_verdict(reading),
            "alarm_required": glue.alarm_required(reading),
            "pick_up": glue.pick_up(request.number("roll", 30.0), request.number("stock", 900.0)),
            "dose": glue.dose(request.number("flow", 4.0), request.number("width", 6.0), request.number("speed", 900.0)),
            "diluted": glue.diluted(request.number("concentration", 8.0), request.number("water", 2.0)),
            "generation": glue.generation(),
            "history": glue.history().to_dict(),
        }
    )


def cal_state(console: Any, request: Request) -> Response:
    return json_response(console.services.cal.view().to_dict())


def cal_model(console: Any, request: Request) -> Response:
    cal = console.services.cal
    return json_response(
        {
            "nip_load": cal.nip_load(request.number("width", 6.0)),
            "nip_impulse": cal.nip_impulse(request.number("dwell", 0.05)),
            "speed_difference": cal.speed_difference(),
            "settled": cal.settled(request.number("tolerance", 1.0)),
            "nip_verdict": cal.nip_verdict(),
            "load": cal.load(),
            "verdict": cal.verdict(),
        }
    )


def reel_state(console: Any, request: Request) -> Response:
    return json_response(console.services.reel.view().to_dict())


def reel_geometry(console: Any, request: Request) -> Response:
    reel = console.services.reel
    core = request.number("core", 150.0)
    thickness = request.number("thickness", 0.08)
    wraps = request.number("wraps", 4000.0)
    built = reel.diameter(core, thickness, wraps)
    return json_response(
        {
            "diameter": built,
            "remaining": reel.remaining(core, thickness, built),
            "length": reel.length(core, thickness, wraps),
            "turn_up": reel.turn_up_verdict(built, request.number("target", built)),
        }
    )


def broke_state(console: Any, request: Request) -> Response:
    return json_response(console.services.broke.view().to_dict())


def broke_model(console: Any, request: Request) -> Response:
    broke = console.services.broke
    return json_response(
        {
            "rate": broke.broke_rate(request.number("volume", 12.0), request.number("seconds", 60.0)),
            "recovery": broke.recovery(request.number("recovered", 9.0), request.number("generated", 12.0)),
            "reprocessed": broke.reprocessed(request.number("volume", 12.0), request.number("consistency", 3.0)),
            "verdict": broke.latch_verdict(request.number("recovered", 9.0), request.number("generated", 12.0)),
            "total": broke.batch_total(),
            "batches": [dict(entry) for entry in broke.batches()],
            "history": broke.history().to_dict(),
        }
    )


def water_state(console: Any, request: Request) -> Response:
    return json_response(console.services.water.view().to_dict())


def water_profile(console: Any, request: Request) -> Response:
    water = console.services.water
    return json_response(
        {
            "profile": water.profile(),
            "average": water.average(),
            "span": water.span(),
            "edge_center": water.edge_center(),
            "at": water.at(request.number("position", 3.0)),
        }
    )


def water_verdict(console: Any, request: Request) -> Response:
    water = console.services.water
    reading = request.number("reading", water.moisture())
    return json_response(
        {
            "verdict": water.moisture_verdict(reading),
            "verdict_of": water.verdict_of(reading),
            "deviation": water.deviation(reading),
            "sustained": water.sustained_dry(reading).to_dict(),
            "generation": water.generation(),
            "history": water.history().to_dict(),
        }
    )


def water_model(console: Any, request: Request) -> Response:
    water = console.services.water
    readings = [float(value) for value in water.values()]
    return json_response(
        {
            "average_of": water.average_of(readings),
            "span_of": water.span_of(readings),
            "band": water.verify_band(request.number("reading", water.moisture()), "moisture"),
            "negative": water.negative(request.number("volume", 0.0), "volume"),
            "sensors": water.map_sensors(),
            "samples": len(water.samples()),
        }
    )


def page(console: Any, request: Request) -> Response:
    name = request.path.lstrip("/") or "index.html"
    return read_page(console.services.config.web_dir, name)
