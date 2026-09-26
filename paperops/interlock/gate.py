"""Gates that require an upstream value to be durable before a downstream action."""

from typing import Any

from ..errors import PreGateError
from ..store import Journal


class PreGate:
    """Refuses a downstream action until the upstream key is committed."""

    def __init__(self, name: str, journal: Journal, key: str) -> None:
        self._name = name
        self._journal = journal
        self._key = key

    @property
    def name(self) -> str:
        return self._name

    @property
    def key(self) -> str:
        return self._key

    def satisfied(self) -> bool:
        return self._journal.has(self._key)

    def require(self) -> Any:
        """Return the committed upstream value or refuse the action."""
        if not self.satisfied():
            raise PreGateError(f"{self._name} needs {self._key} to be durable first")
        return self._journal.require(self._key)
