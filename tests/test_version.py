"""Generations, expiring artifacts and short-lived confirmations."""

import pytest

from paperops.clock import IdSequence, LogicalClock
from paperops.errors import ConfirmationMismatchError, StaleArtifactError, UnknownConfirmationError
from paperops.version import Artifacts, Confirmations, Generations


def test_generations_move_forward_and_refuse_stale(journal):
    generations = Generations(journal)
    assert generations.current("dry.curve") == 0
    assert generations.advance("dry.curve", "dry-curve") == 1
    assert generations.is_current("dry.curve", 1) is True
    generations.require_current("dry.curve", 1, "curve")
    assert generations.advance("dry.curve", "dry-curve") == 2
    with pytest.raises(StaleArtifactError):
        generations.require_current("dry.curve", 1, "curve")
    assert generations.all()["dry.curve"] == 2


def test_artifacts_refuse_missing_and_stale(journal):
    clock = LogicalClock()
    generations = Generations(journal)
    artifacts = Artifacts(journal, clock)
    with pytest.raises(StaleArtifactError):
        artifacts.require_current("snapshot", "control.snapshot", 10, generations)
    generation = generations.advance("control.snapshot", "state-snapshot")
    artifacts.record("snapshot", "control.snapshot", generation, "digest-a")
    ref = artifacts.require_current("snapshot", "control.snapshot", 10, generations)
    assert ref.digest == "digest-a"
    assert artifacts.age("snapshot", "control.snapshot") == 0
    assert artifacts.stale("snapshot", "control.snapshot", 10, generations) is False
    generations.advance("control.snapshot", "state-snapshot")
    assert artifacts.stale("snapshot", "control.snapshot", 10, generations) is True


def test_confirmations_round_trip(journal):
    clock = LogicalClock()
    generations = Generations(journal)
    confirmations = Confirmations(journal, clock, IdSequence("cfm"), generations)
    confirmation = confirmations.issue("dry.curve", "dry", 5)
    assert confirmation.confirmation_id == "cfm-000001"
    redeemed = confirmations.redeem("cfm-000001", "dry.curve", "dry")
    assert redeemed.subject == "dry"
    assert confirmations.outstanding() == (redeemed,)


def test_confirmation_subject_and_generation_are_bound(journal):
    clock = LogicalClock()
    generations = Generations(journal)
    confirmations = Confirmations(journal, clock, IdSequence("cfm"), generations)
    confirmations.issue("dry.curve", "dry", 5)
    with pytest.raises(ConfirmationMismatchError):
        confirmations.redeem("cfm-000001", "dry.curve", "steam")
    generations.advance("dry.curve", "dry-curve")
    with pytest.raises(StaleArtifactError):
        confirmations.redeem("cfm-000001", "dry.curve", "dry")


def test_confirmation_expires_and_unknown_is_refused(journal):
    clock = LogicalClock()
    generations = Generations(journal)
    confirmations = Confirmations(journal, clock, IdSequence("cfm"), generations)
    confirmation = confirmations.issue("dry.curve", "dry", 1)
    assert confirmations.is_expired(confirmation) is False
    clock.advance(2)
    assert confirmations.is_expired(confirmation) is True
    assert confirmations.outstanding() == ()
    with pytest.raises(StaleArtifactError):
        confirmations.redeem("cfm-000001", "dry.curve", "dry")
    with pytest.raises(UnknownConfirmationError):
        confirmations.redeem("cfm-999999", "dry.curve", "dry")
