"""Event capture and filtered history queries."""

from paperops.verdict import RecordFilter

from support import ok, run_line


def test_audit_captures_published_events(console, services):
    ok(console, "POST", "/api/steam/drain", {})
    ok(console, "POST", "/api/steam/valve", {"open": True})
    assert services.audit.count("steam.drained") == 1
    assert services.audit.count("steam.valve.changed") == 1
    assert services.audit.sequence >= 2


def test_audit_query_narrows_by_topic(console, services):
    ok(console, "POST", "/api/steam/drain", {})
    records = services.audit.by_topic("steam.drained")
    assert len(records) == 1
    assert records[0].topic == "steam.drained"
    assert services.audit.query(RecordFilter(topic="missing.topic")) == []


def test_audit_summary_and_news(console, services):
    run_line(console)
    summary = services.audit.summary()
    assert summary["total"] > 0
    assert summary["topics"]["dry.speed.set"] == 1
    news = services.audit.news(3)
    assert len(news) == 3
    assert news[0].seq > news[-1].seq


def test_audit_clear_empties_the_stream(console, services):
    ok(console, "POST", "/api/steam/drain", {})
    assert services.audit.clear() >= 1
    assert services.audit.records() == ()
    assert services.audit.summary()["total"] == 0
