"""Latches whose transitions need every declared condition to agree."""

from typing import Any, Mapping, Sequence

from ..errors import LatchClearError, LatchSetError


class Latch:
    """A set/clear interlock with named conditions on each transition."""

    def __init__(
        self,
        name: str,
        set_conditions: Sequence[str],
        clear_conditions: Sequence[str],
    ) -> None:
        if not set_conditions or not clear_conditions:
            raise ValueError("a latch needs set and clear conditions")
        self._name = name
        self._set_conditions = tuple(set_conditions)
        self._clear_conditions = tuple(clear_conditions)
        self._set = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_set(self) -> bool:
        return self._set

    def unmet_set_conditions(self, conditions: Mapping[str, bool]) -> tuple[str, ...]:
        return tuple(name for name in self._set_conditions if not conditions.get(name, False))

    def unmet_clear_conditions(self, conditions: Mapping[str, bool]) -> tuple[str, ...]:
        return tuple(name for name in self._clear_conditions if not conditions.get(name, False))

    def set(self, conditions: Mapping[str, bool]) -> None:
        unmet = self.unmet_set_conditions(conditions)
        if unmet:
            raise LatchSetError(f"{self._name} cannot latch, unmet: {', '.join(unmet)}")
        self._set = True

    def clear(self, conditions: Mapping[str, bool]) -> None:
        unmet = self.unmet_clear_conditions(conditions)
        if unmet:
            raise LatchClearError(f"{self._name} cannot clear, unmet: {', '.join(unmet)}")
        self._set = False

    def restore(self, value: bool) -> None:
        """Adopt a latch position recovered from the record stream."""
        self._set = bool(value)

    def state(self) -> dict[str, Any]:
        return {
            "latch": self._name,
            "set": self._set,
            "set_conditions": list(self._set_conditions),
            "clear_conditions": list(self._clear_conditions),
        }
