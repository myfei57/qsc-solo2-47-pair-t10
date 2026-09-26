"""Commit watermark, batching, rollback and restart replay."""

import pytest

from paperops.errors import (
    BatchNotPendingError,
    CommitOrderError,
    MaintenanceError,
    RollbackError,
)
from paperops.store import Journal


def test_append_before_open_is_refused(journal):
    with pytest.raises(BatchNotPendingError):
        journal.append("press/state", {"load": 1.0}, "missing")


def test_commit_publishes_and_moves_the_watermark(journal):
    journal.open("a")
    journal.append("press/state", {"load": 1.0}, "a")
    assert journal.read("press/state") is None
    assert journal.commit("a") == 1
    assert journal.read("press/state") == {"load": 1.0}


def test_commit_refuses_to_jump_an_earlier_open_batch(journal):
    journal.open("a")
    journal.append("press/state", {"load": 1.0}, "a")
    journal.open("b")
    journal.append("dry/speed", {"speed": 10.0}, "b")
    with pytest.raises(CommitOrderError):
        journal.commit("b")


def test_discard_keeps_rows_out_of_the_view(journal):
    journal.open("a")
    journal.append("press/state", {"load": 1.0}, "a")
    assert journal.discard("a") == 1
    assert journal.read("press/state") is None
    assert journal.aborted_batches() == ("a",)


def test_rollback_restores_the_previous_committed_value(journal):
    journal.open("a")
    journal.append("press/state", {"load": 1.0}, "a")
    journal.commit("a")
    journal.open("b")
    journal.append("press/state", {"load": 2.0}, "b")
    journal.commit("b")
    assert journal.read("press/state") == {"load": 2.0}
    assert journal.rollback("b") == 1
    assert journal.read("press/state") == {"load": 1.0}


def test_rollback_of_an_unknown_batch_is_refused(journal):
    with pytest.raises(RollbackError):
        journal.rollback("never-existed")


def test_transaction_rolls_back_on_error(journal):
    with pytest.raises(RuntimeError):
        with journal.transaction("press") as batch:
            journal.append("press/state", {"load": 1.0}, batch)
            raise RuntimeError("boom")
    assert journal.read("press/state") is None
    assert journal.aborted_batches()


def test_maintenance_mode_freezes_writes(journal):
    journal.open("a")
    journal.set_read_only(True)
    with pytest.raises(MaintenanceError):
        journal.append("press/state", {"load": 1.0}, "a")
    journal.set_read_only(False)
    journal.append("press/state", {"load": 1.0}, "a")
    journal.commit("a")
    assert journal.read("press/state") == {"load": 1.0}


def test_restart_replays_only_entries_at_or_below_the_watermark(tmp_path):
    directory = str(tmp_path / "stream")
    first = Journal(directory)
    first.open("a")
    first.append("press/state", {"load": 1.0}, "a")
    first.commit("a")
    first.open("b")
    first.append("dry/speed", {"speed": 900.0}, "b")

    second = Journal(directory)
    assert second.read("press/state") == {"load": 1.0}
    assert second.read("dry/speed") is None
    assert second.pending_batches() == ("b",)


def test_restart_recovers_the_digest_of_the_committed_view(tmp_path):
    directory = str(tmp_path / "stream")
    first = Journal(directory)
    first.open("a")
    first.append("press/state", {"load": 1.0}, "a")
    first.append("dry/speed", {"speed": 900.0}, "a")
    first.commit("a")
    digest = first.snapshot().digest

    second = Journal(directory)
    assert second.snapshot().digest == digest


def test_restart_keeps_aborted_batch_out_of_the_view(tmp_path):
    directory = str(tmp_path / "stream")
    first = Journal(directory)
    first.open("a")
    first.append("press/state", {"load": 1.0}, "a")
    first.discard("a")

    second = Journal(directory)
    assert second.read("press/state") is None
    assert second.aborted_batches() == ("a",)


def test_history_returns_every_committed_row_for_a_key(journal):
    journal.open("a")
    journal.append("press/state", {"load": 1.0}, "a")
    journal.commit("a")
    journal.open("b")
    journal.append("press/state", {"load": 2.0}, "b")
    journal.commit("b")
    history = journal.history("press/state")
    assert [entry.value for entry in history] == [{"load": 1.0}, {"load": 2.0}]
    assert journal.generation_of("press/state") == 0
