"""Curve handover: parallel blending window between the old and the new curve."""

from support import build, issue_confirmation, ok, refused


def run_procedure(console) -> None:
    """Drive the drying procedure to completion once, as a running line would."""
    ok(console, "POST", "/api/steam/drain", {})
    ok(console, "POST", "/api/steam/valve", {"open": True})
    ok(console, "POST", "/api/dry/begin", {})
    ok(console, "POST", "/api/dry/drain", {})
    ok(console, "POST", "/api/dry/admit", {})
    ok(console, "POST", "/api/dry/warm", {})
    ok(console, "POST", "/api/dry/run", {})


def set_curve(console, slope: float, base: float) -> None:
    ok(
        console,
        "POST",
        "/api/dry/curve",
        {
            "slope": slope,
            "base": base,
            "confirmation_id": issue_confirmation(console, "dry.curve", "dry"),
        },
    )


def begin_handover(console, slope: float, base: float, steps: int = 2) -> dict:
    return ok(
        console,
        "POST",
        "/api/dry/handover/begin",
        {
            "slope": slope,
            "base": base,
            "steps": steps,
            "confirmation_id": issue_confirmation(console, "dry.curve", "dry"),
        },
    )


def test_handover_blends_while_the_committed_curve_stays_old(console, services):
    set_curve(console, 1.0, 0.0)
    body = begin_handover(console, 2.0, 1.0, steps=2)
    assert body["status"] == "open"
    assert body["weight"] == 0.0
    # authority: the committed curve is still the old one
    assert services.dry.curve()["slope"] == 1.0
    assert services.dry.curve()["generation"] == 1
    assert services.dry.effective_curve()["slope"] == 1.0

    body = ok(console, "POST", "/api/dry/handover/advance", {})
    assert body["weight"] == 0.5
    # the section model follows the journaled blend, the committed curve does not move
    assert services.dry.effective_curve()["slope"] == 1.5
    assert services.dry.effective_curve()["base"] == 0.5
    assert services.dry.curve()["slope"] == 1.0
    assert services.dry.curve()["generation"] == 1


def test_handover_completes_when_the_weight_reaches_full(console, services):
    set_curve(console, 1.0, 0.0)
    begin_handover(console, 2.0, 1.0, steps=2)
    ok(console, "POST", "/api/dry/handover/advance", {})
    body = ok(console, "POST", "/api/dry/handover/advance", {})
    assert body["status"] == "complete"
    assert body["weight"] == 1.0
    # the new curve is committed under a fresh generation in the same step
    assert services.dry.curve() == {"slope": 2.0, "base": 1.0, "generation": 2}
    assert services.dry.effective_curve()["slope"] == 2.0
    assert services.dry.handover_open() is False


def test_open_handover_locks_the_curve_target(console, services):
    set_curve(console, 1.0, 0.0)
    begin_handover(console, 2.0, 1.0)

    response = refused(
        console,
        "POST",
        "/api/dry/curve",
        {
            "slope": 1.8,
            "base": 0.4,
            "confirmation_id": issue_confirmation(console, "dry.curve", "dry"),
        },
    )
    assert response.status == 409
    assert "handover is still open" in response.body["error"]

    response = refused(console, "POST", "/api/dry/handover/begin", {
        "slope": 1.8,
        "base": 0.4,
        "steps": 2,
        "confirmation_id": issue_confirmation(console, "dry.curve", "dry"),
    })
    assert response.status == 409

    response = refused(console, "POST", "/api/dry/begin", {})
    assert response.status == 409
    assert "handover is still open" in response.body["error"]

    # the lock lifts once the open handover is closed
    ok(console, "POST", "/api/dry/handover/abort", {})
    assert services.dry.handover_open() is False
    ok(console, "POST", "/api/dry/begin", {})


def test_settle_commits_the_blend_reached_so_far(console, services):
    set_curve(console, 1.0, 0.0)
    begin_handover(console, 3.0, 2.0, steps=4)
    ok(console, "POST", "/api/dry/handover/advance", {})
    ok(console, "POST", "/api/dry/handover/advance", {})
    body = ok(console, "POST", "/api/dry/handover/settle", {})
    assert body["status"] == "settled"
    assert body["weight"] == 0.5
    # the blend at the settled weight becomes the committed curve
    assert services.dry.curve() == {"slope": 2.0, "base": 1.0, "generation": 2}
    assert services.dry.handover_open() is False


def test_abort_keeps_the_old_curve_in_force(console, services):
    set_curve(console, 1.0, 0.0)
    begin_handover(console, 3.0, 2.0, steps=4)
    ok(console, "POST", "/api/dry/handover/advance", {})
    body = ok(console, "POST", "/api/dry/handover/abort", {})
    assert body["status"] == "aborted"
    assert body["weight"] == 0.25
    # no curve commit, no generation move
    assert services.dry.curve() == {"slope": 1.0, "base": 0.0, "generation": 1}
    assert services.dry.effective_curve()["slope"] == 1.0
    assert services.dry.handover_weight() == 0.0


def test_handover_steps_need_an_open_handover(console):
    for path in ("/api/dry/handover/advance", "/api/dry/handover/settle", "/api/dry/handover/abort"):
        response = refused(console, "POST", path, {})
        assert response.status == 409
        assert "no curve handover is open" in response.body["error"]


def test_handover_begin_needs_a_confirmation(console):
    response = refused(
        console,
        "POST",
        "/api/dry/handover/begin",
        {"slope": 2.0, "base": 1.0, "steps": 2, "confirmation_id": "cfm-999999"},
    )
    assert response.status == 404


def test_handover_begin_checks_the_slope_band(console):
    response = refused(
        console,
        "POST",
        "/api/dry/handover/begin",
        {
            "slope": 30.0,
            "base": 1.0,
            "steps": 2,
            "confirmation_id": issue_confirmation(console, "dry.curve", "dry"),
        },
    )
    assert response.status == 422


def test_interrupted_handover_resumes_from_the_journal(config):
    first = build(config)
    set_curve(first.console, 1.0, 0.0)
    begin_handover(first.console, 3.0, 2.0, steps=4)
    ok(first.console, "POST", "/api/dry/handover/advance", {})
    ok(first.console, "POST", "/api/dry/handover/advance", {})

    # the restart recovers the open handover at its last committed weight
    second = build(config)
    assert second.dry.handover_open() is True
    assert second.dry.handover_weight() == 0.5
    assert second.dry.effective_curve()["slope"] == 2.0
    assert second.dry.curve()["slope"] == 1.0

    # and it closes out without running the drying procedure again
    assert second.dry.procedure()["completed"] == []
    ok(second.console, "POST", "/api/dry/handover/advance", {})
    body = ok(second.console, "POST", "/api/dry/handover/advance", {})
    assert body["status"] == "complete"
    assert second.dry.curve() == {"slope": 3.0, "base": 2.0, "generation": 2}


def test_interrupted_handover_can_settle_after_a_restart(config):
    first = build(config)
    set_curve(first.console, 1.0, 0.0)
    begin_handover(first.console, 3.0, 2.0, steps=4)
    ok(first.console, "POST", "/api/dry/handover/advance", {})

    second = build(config)
    body = ok(second.console, "POST", "/api/dry/handover/settle", {})
    assert body["status"] == "settled"
    assert second.dry.curve() == {"slope": 1.5, "base": 0.5, "generation": 2}


def test_a_fresh_handover_may_begin_after_the_previous_one_closed(console, services):
    set_curve(console, 1.0, 0.0)
    begin_handover(console, 2.0, 1.0, steps=1)
    body = ok(console, "POST", "/api/dry/handover/advance", {})
    assert body["status"] == "complete"
    begin_handover(console, 1.4, 0.3, steps=1)
    assert services.dry.handover()["old"]["slope"] == 2.0


def test_handover_is_visible_in_the_state_and_model(console, services):
    run_procedure(console)
    set_curve(console, 1.0, 0.0)
    begin_handover(console, 2.0, 1.0, steps=2)
    ok(console, "POST", "/api/dry/handover/advance", {})

    state = ok(console, "GET", "/api/dry/state")
    assert state["handover"]["status"] == "open"
    assert state["handover"]["weight"] == 0.5
    assert state["slope"] == 1.0

    handover = ok(console, "GET", "/api/dry/handover")
    assert handover["open"] is True
    assert handover["weight"] == 0.5
    assert handover["curve"]["slope"] == 1.0
    assert handover["effective"]["slope"] == 1.5

    # the section model follows the blend during the window
    model = ok(console, "GET", "/api/dry/model?temperature=100")
    assert model["evaporation"] == 150.5
