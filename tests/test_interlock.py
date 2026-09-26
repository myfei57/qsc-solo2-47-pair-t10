"""Durability gates, latches and ordered procedures."""

import pytest

from paperops.errors import (
    DuplicateStageError,
    LatchClearError,
    LatchSetError,
    OutOfSequenceError,
    PreGateError,
    UnknownStageError,
)
from paperops.interlock import Latch, PreGate, StageSequence


def test_pre_gate_refuses_until_the_key_is_durable(journal):
    gate = PreGate("dry.speed", journal, "press/state")
    assert gate.satisfied() is False
    with pytest.raises(PreGateError):
        gate.require()
    journal.open("a")
    journal.append("press/state", {"load": 1.0}, "a")
    journal.commit("a")
    assert gate.satisfied() is True
    assert gate.require() == {"load": 1.0}
    assert gate.name == "dry.speed"
    assert gate.key == "press/state"


def test_latch_needs_every_set_condition():
    latch = Latch("broke.handling", set_conditions=("broken",), clear_conditions=("handled",))
    assert latch.is_set is False
    with pytest.raises(LatchSetError):
        latch.set({"broken": False})
    latch.set({"broken": True})
    assert latch.is_set is True
    assert latch.unmet_set_conditions({"broken": True}) == ()
    assert latch.unmet_clear_conditions({"handled": False}) == ("handled",)


def test_latch_needs_every_clear_condition():
    latch = Latch("glue.alarm", set_conditions=("lifted",), clear_conditions=("lifted", "stopped"))
    latch.set({"lifted": True})
    with pytest.raises(LatchClearError):
        latch.clear({"lifted": True, "stopped": False})
    latch.clear({"lifted": True, "stopped": True})
    assert latch.is_set is False
    latch.restore(True)
    assert latch.state()["set"] is True


def test_stage_sequence_enforces_order():
    procedure = StageSequence("dry.procedure", ("drain", "steam", "warm", "dry"))
    assert procedure.next_required() == "drain"
    with pytest.raises(UnknownStageError):
        procedure.advance("purge")
    with pytest.raises(OutOfSequenceError):
        procedure.advance("warm")
    procedure.advance("drain")
    procedure.advance("steam")
    with pytest.raises(DuplicateStageError):
        procedure.advance("steam")
    assert procedure.completed() == ("drain", "steam")
    assert procedure.is_done("drain") is True
    assert procedure.stages() == ("drain", "steam", "warm", "dry")


def test_stage_sequence_reset_and_complete_state():
    procedure = StageSequence("broke.procedure", ("break", "process"))
    procedure.advance("break")
    procedure.advance("process")
    assert procedure.next_required() is None
    assert procedure.state()["next"] == "complete"
    procedure.reset()
    assert procedure.completed() == ()
    assert procedure.next_required() == "break"
