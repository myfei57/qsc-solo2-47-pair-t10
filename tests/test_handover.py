"""Grade-change handover: overlap, authority, lock and interruption wrap-up."""

from support import build, issue_confirmation, ok, refused


def _run_dryer(console) -> None:
    """Bring the dryer row up to a running, heated section."""
    ok(console, "POST", "/api/steam/drain", {})
    ok(console, "POST", "/api/steam/valve", {"open": True})
    ok(console, "POST", "/api/dry/begin", {})
    ok(console, "POST", "/api/dry/drain", {})
    ok(console, "POST", "/api/dry/admit", {})
    ok(console, "POST", "/api/dry/warm", {})
    ok(console, "POST", "/api/dry/run", {})
    ok(console, "POST", "/api/dry/heat", {"target": 120})


def _begin_handover(console, slope=3.0, base=1.0, blend_ticks=4, confirm_ticks=2):
    return ok(
        console,
        "POST",
        "/api/dry/handover/begin",
        {
            "slope": slope,
            "base": base,
            "confirmation_id": issue_confirmation(console, "dry.curve", "dry"),
            "blend_ticks": blend_ticks,
            "confirm_ticks": confirm_ticks,
        },
    )


def test_handover_blends_then_commits(console, services):
    _run_dryer(console)
    ok(
        console,
        "POST",
        "/api/dry/curve",
        {"slope": 1.0, "base": 0.0, "confirmation_id": issue_confirmation(console, "dry.curve", "dry")},
    )
    body = _begin_handover(console)
    assert body["state"] == "blending"
    assert body["authority"] == "blend"
    assert body["alpha"] == 0.0
    assert body["effective"]["slope"] == 1.0

    body = ok(console, "POST", "/api/dry/handover/tick", {})
    assert body["alpha"] == 0.25
    assert body["effective"]["slope"] == 1.5
    body = ok(console, "POST", "/api/dry/handover/tick", {})
    assert body["alpha"] == 0.5
    assert body["effective"]["slope"] == 2.0
    ok(console, "POST", "/api/dry/handover/tick", {})
    body = ok(console, "POST", "/api/dry/handover/tick", {})
    assert body["state"] == "confirm"
    assert body["alpha"] == 1.0
    assert body["confirm_reference"] == 120.0

    body = ok(console, "POST", "/api/dry/handover/tick", {})
    assert body["state"] == "confirm"
    assert body["confirm_streak"] == 1
    body = ok(console, "POST", "/api/dry/handover/tick", {})
    assert body["state"] == "committed"
    assert body["authority"] == "new-curve"

    assert services.dry.curve()["slope"] == 3.0
    assert services.dry.curve()["generation"] == 2
    assert ok(console, "GET", "/api/dry/model?temperature=100")["evaporation"] == 301.0
    state = ok(console, "GET", "/api/dry/state")
    assert state["effective"]["slope"] == 3.0
    assert state["handover"]["state"] == "committed"


def test_handover_locks_the_target_until_it_closes(console, services):
    _run_dryer(console)
    _begin_handover(console, blend_ticks=2, confirm_ticks=1)
    response = refused(
        console,
        "POST",
        "/api/dry/curve",
        {"slope": 1.5, "base": 0.0, "confirmation_id": issue_confirmation(console, "dry.curve", "dry")},
    )
    assert response.status == 409
    assert "locked" in response.body["error"]
    assert refused(console, "POST", "/api/dry/handover/begin", {"slope": 2.0, "base": 0.0, "confirmation_id": "x"}).status == 409
    assert refused(console, "POST", "/api/dry/begin", {}).status == 409

    ok(console, "POST", "/api/dry/handover/tick", {})
    ok(console, "POST", "/api/dry/handover/tick", {})
    assert ok(console, "POST", "/api/dry/handover/tick", {})["state"] == "committed"
    ok(
        console,
        "POST",
        "/api/dry/curve",
        {"slope": 1.5, "base": 0.0, "confirmation_id": issue_confirmation(console, "dry.curve", "dry")},
    )
    assert services.dry.curve()["slope"] == 1.5


def test_suspended_handover_holds_the_frozen_blend(console, services):
    _run_dryer(console)
    _begin_handover(console, blend_ticks=4, confirm_ticks=1)
    ok(console, "POST", "/api/dry/handover/tick", {})
    ok(console, "POST", "/api/dry/handover/tick", {})
    body = ok(console, "POST", "/api/dry/handover/suspend", {"reason": "sheet break"})
    assert body["state"] == "suspended"
    assert body["authority"] == "frozen-blend"
    assert body["frozen_temperature"] == 120.0

    assert refused(console, "POST", "/api/dry/handover/tick", {}).status == 409
    assert services.dry.effective_curve()["slope"] == 2.0

    body = ok(console, "POST", "/api/dry/handover/resume", {})
    assert body["state"] == "blending"
    body = ok(console, "POST", "/api/dry/handover/tick", {})
    assert body["progress"] == 3
    assert body["alpha"] == 0.75


def test_open_handover_survives_a_restart_as_suspended(config):
    first = build(config)
    _run_dryer(first.console)
    _begin_handover(first.console, blend_ticks=4, confirm_ticks=1)
    ok(first.console, "POST", "/api/dry/handover/tick", {})
    ok(first.console, "POST", "/api/dry/handover/tick", {})

    second = build(config)
    record = ok(second.console, "GET", "/api/dry/handover")["handover"]
    assert record["state"] == "suspended"
    assert record["reason"] == "restart"
    assert record["progress"] == 2
    assert record["alpha"] == 0.5

    ok(second.console, "POST", "/api/dry/handover/resume", {})
    ok(second.console, "POST", "/api/dry/handover/tick", {})
    ok(second.console, "POST", "/api/dry/handover/tick", {})
    body = ok(second.console, "POST", "/api/dry/handover/tick", {})
    assert body["state"] == "committed"
    assert second.dry.curve()["slope"] == 3.0


def test_complete_now_finishes_a_suspended_handover(console, services):
    _run_dryer(console)
    _begin_handover(console)
    ok(console, "POST", "/api/dry/handover/tick", {})
    ok(console, "POST", "/api/dry/handover/suspend", {})
    body = ok(console, "POST", "/api/dry/handover/complete", {})
    assert body["state"] == "committed"
    assert services.dry.curve()["slope"] == 3.0
    assert services.dry.curve()["generation"] == 1


def test_complete_now_refuses_a_moved_temperature(console, services):
    _run_dryer(console)
    _begin_handover(console)
    ok(console, "POST", "/api/dry/handover/tick", {})
    ok(console, "POST", "/api/dry/handover/suspend", {})
    ok(console, "POST", "/api/dry/heat", {"target": 130})
    response = refused(console, "POST", "/api/dry/handover/complete", {})
    assert response.status == 409
    assert "frozen handover point" in response.body["error"]

    body = ok(console, "POST", "/api/dry/handover/abort", {"reason": "grade change cancelled"})
    assert body["state"] == "aborted"
    assert body["authority"] == "old-curve"
    assert services.dry.curve()["slope"] == 1.0
    assert services.dry.curve()["generation"] == 0
    assert _begin_handover(console)["state"] == "blending"


def test_confirm_streak_resets_when_temperature_leaves_the_band(console, services):
    _run_dryer(console)
    _begin_handover(console, blend_ticks=2, confirm_ticks=2)
    ok(console, "POST", "/api/dry/handover/tick", {})
    body = ok(console, "POST", "/api/dry/handover/tick", {})
    assert body["state"] == "confirm"

    ok(console, "POST", "/api/dry/heat", {"target": 125})
    body = ok(console, "POST", "/api/dry/handover/tick", {})
    assert body["confirm_streak"] == 0
    ok(console, "POST", "/api/dry/heat", {"target": 120})
    body = ok(console, "POST", "/api/dry/handover/tick", {})
    assert body["confirm_streak"] == 1
    body = ok(console, "POST", "/api/dry/handover/tick", {})
    assert body["state"] == "committed"


def test_closing_the_steam_valve_suspends_the_handover(console, services):
    _run_dryer(console)
    _begin_handover(console)
    ok(console, "POST", "/api/dry/handover/tick", {})
    ok(console, "POST", "/api/steam/valve", {"open": False})
    record = ok(console, "GET", "/api/dry/handover")["handover"]
    assert record["state"] == "suspended"
    assert record["reason"] == "steam valve closed"


def test_handover_begin_needs_a_confirmation_and_a_sane_slope(console, services):
    _run_dryer(console)
    response = refused(
        console,
        "POST",
        "/api/dry/handover/begin",
        {"slope": 3.0, "base": 1.0, "confirmation_id": "cfm-999999"},
    )
    assert response.status == 404
    response = refused(
        console,
        "POST",
        "/api/dry/handover/begin",
        {
            "slope": 0.01,
            "base": 1.0,
            "confirmation_id": issue_confirmation(console, "dry.curve", "dry"),
        },
    )
    assert response.status == 422


def test_handover_operations_need_an_open_handover(console, services):
    _run_dryer(console)
    for path in ("tick", "suspend", "resume", "complete", "abort"):
        response = refused(console, "POST", f"/api/dry/handover/{path}", {})
        assert response.status == 404
    assert ok(console, "GET", "/api/dry/handover")["handover"] is None
