"""Shared helpers for the control service tests."""

import json
import os

from paperops.config import Config
from paperops.console.http import Request, Response

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


def build(config: Config):
    from paperops.app import build_services

    return build_services(config)


def call(console, method: str, path: str, body=None) -> Response:
    text = "" if body is None else json.dumps(body)
    return console.handle(Request.parse(method, path, text))


def call_raw(console, method: str, path: str, text: str) -> Response:
    """Send a body exactly as given, for malformed payload checks."""
    return console.handle(Request.parse(method, path, text))


def ok(console, method: str, path: str, body=None):
    response = call(console, method, path, body)
    assert response.status == 200, response.body
    return response.body


def refused(console, method: str, path: str, body=None) -> Response:
    response = call(console, method, path, body)
    assert response.status >= 400, response.body
    return response


def issue_confirmation(console, name: str, subject: str, ttl_ticks: int = 20) -> str:
    body = ok(
        console,
        "POST",
        "/api/confirmation",
        {"name": name, "subject": subject, "ttl_ticks": ttl_ticks},
    )
    return body["confirmation_id"]


def advance_clock(console, steps: int = 1) -> int:
    return ok(console, "POST", "/api/clock/advance", {"steps": steps})["tick"]


def run_line(console) -> None:
    """Drive one full line from a cold start through a completed spool transfer."""
    ok(console, "POST", "/api/clock/advance", {"steps": 1})
    ok(console, "POST", "/api/press/load", {"load": 45})
    ok(console, "POST", "/api/press/dewater", {"inlet_moisture": 60, "width": 6})
    ok(console, "POST", "/api/press/persist", {"speed": 900})
    ok(console, "POST", "/api/steam/drain", {})
    ok(console, "POST", "/api/steam/valve", {"open": True})
    ok(console, "POST", "/api/dry/begin", {})
    ok(console, "POST", "/api/dry/drain", {})
    ok(console, "POST", "/api/dry/admit", {})
    ok(console, "POST", "/api/dry/warm", {})
    ok(console, "POST", "/api/dry/run", {})
    ok(console, "POST", "/api/dry/heat", {"target": 120})
    ok(console, "POST", "/api/dry/speed", {"speed": 900})
    ok(console, "POST", "/api/glue/roll", {"lifted": True})
    ok(console, "POST", "/api/glue/stop", {})
    ok(console, "POST", "/api/cal/speed", {"speed": 900, "target": 900})
    ok(console, "POST", "/api/cal/nip", {"closed": True, "pressure": 60})
    ok(console, "POST", "/api/reel/change", {"reason": "full spool"})
    ok(console, "POST", "/api/reel/spool", {"spool_id": "S-1"})
    ok(console, "POST", "/api/reel/retract", {})
    ok(console, "POST", "/api/reel/bite", {})
