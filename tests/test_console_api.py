"""Routing, status mapping and page delivery."""

from paperops.console.pages import page_names

from support import call, call_raw, ok, refused


def test_unknown_route_is_not_found(console):
    response = call(console, "GET", "/api/does-not-exist")
    assert response.status == 404


def test_wrong_method_is_not_found(console):
    response = call(console, "GET", "/api/press/load")
    assert response.status == 404


def test_malformed_body_is_a_bad_request(console):
    response = call_raw(console, "POST", "/api/press/load", "{not json")
    assert response.status == 400
    assert "malformed request" in response.body["error"]


def test_missing_field_is_a_bad_request(console):
    response = refused(console, "POST", "/api/confirmation", {"subject": "dry"})
    assert response.status == 400


def test_out_of_range_maps_to_unprocessable(console):
    response = refused(console, "POST", "/api/press/dewater", {"inlet_moisture": 200})
    assert response.status == 422


def test_health_reports_the_store(console):
    body = ok(console, "GET", "/healthz")
    assert body["status"] == "ok"
    assert body["watermark"] == 0
    assert body["committed_keys"] == 0


def test_canonical_design_routes_are_registered(console):
    routes = set(console.routes())
    for method, path in (
        ("POST", "/api/dry/speed"),
        ("POST", "/api/steam/valve"),
        ("POST", "/api/glue/stop"),
        ("POST", "/api/reel/change"),
        ("POST", "/api/broke/reset"),
        ("GET", "/api/state"),
    ):
        assert (method, path) in routes


def test_pages_are_named_and_served(console):
    assert set(page_names()) == {
        "index.html",
        "operations.html",
        "curves.html",
        "audit.html",
    }
    for name in page_names():
        response = call(console, "GET", "/" + name)
        assert response.status == 200
    assert call(console, "GET", "/missing.html").status == 404
