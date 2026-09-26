"""Consolidated read model, counters and the expiring snapshot."""

import pytest

from paperops.errors import StaleArtifactError
from paperops.event import ALL_TOPICS

from support import issue_confirmation, ok


def test_view_aggregates_every_subsystem(services):
    view = services.state.view().to_dict()
    assert set(view["subsystems"]) == {
        "press",
        "dry",
        "steam",
        "glue",
        "cal",
        "reel",
        "broke",
        "water",
    }
    assert view["tick"] == 0
    assert view["committed_keys"] == 0


def test_counters_cover_every_declared_topic(services):
    counters = services.state.counters()
    assert set(counters) == set(ALL_TOPICS)
    assert counters["dry.speed.set"] == 0


def test_snapshot_records_and_requires_a_current_artifact(services):
    before = services.journal.watermark
    body = services.state.snapshot()
    assert body["snapshot"]["watermark"] == before
    ref = services.state.require_snapshot(100)
    assert ref.name == "control.snapshot"
    assert ref.digest == body["artifact"]["digest"]


def test_snapshot_expires_when_a_parameter_generation_moves(console, services):
    services.state.snapshot()
    confirmation = issue_confirmation(console, "dry.curve", "dry")
    ok(console, "POST", "/api/dry/curve", {"slope": 1.4, "base": 0.2, "confirmation_id": confirmation})
    with pytest.raises(StaleArtifactError):
        services.state.require_snapshot(100)


def test_verdict_history_is_reported_per_subject(console, services):
    assert services.state.histories() == (
        "broke.handling",
        "glue.concentration",
        "press.dryness",
        "steam.pressure",
        "water.moisture",
    )
    ok(console, "GET", "/api/press/model")
    history = services.state.verdict_history("press.dryness")
    assert history["subject"] == "press.dryness"
    assert services.state.verdict_history("unknown.subject")["current"] == "unknown"
