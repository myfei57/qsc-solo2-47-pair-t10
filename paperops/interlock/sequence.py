"""Ordered multi-stage procedures."""

from typing import Any, Sequence

from ..errors import DuplicateStageError, OutOfSequenceError, UnknownStageError

COMPLETE = "complete"


class StageSequence:
    """An ordered procedure; a stage opens only after every earlier stage closed."""

    def __init__(self, name: str, stages: Sequence[str]) -> None:
        if not stages:
            raise ValueError("a procedure needs at least one stage")
        self._name = name
        self._stages = tuple(stages)
        self._done: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    def stages(self) -> tuple[str, ...]:
        return self._stages

    def completed(self) -> tuple[str, ...]:
        return tuple(self._done)

    def is_done(self, stage: str) -> bool:
        return stage in self._done

    def next_required(self) -> str | None:
        for stage in self._stages:
            if stage not in self._done:
                return stage
        return None

    def advance(self, stage: str) -> str:
        """Close a stage, refusing anything that jumps the order."""
        if stage not in self._stages:
            raise UnknownStageError(f"{self._name} does not declare stage {stage}")
        if stage in self._done:
            raise DuplicateStageError(f"{self._name} stage {stage} already closed")
        for earlier in self._stages[: self._stages.index(stage)]:
            if earlier not in self._done:
                raise OutOfSequenceError(
                    f"{self._name} cannot close {stage} before {earlier}"
                )
        self._done.append(stage)
        return stage

    def reset(self) -> None:
        self._done = []

    def state(self) -> dict[str, Any]:
        return {
            "procedure": self._name,
            "stages": list(self._stages),
            "completed": list(self.completed()),
            "next": self.next_required() or COMPLETE,
        }
