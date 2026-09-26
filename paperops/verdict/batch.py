"""Uniqueness of recorded process batches."""

from typing import Any, Mapping

from ..errors import DuplicateBatchError, UnknownBatchError
from ..store import Journal, keys


class BatchRegistry:
    """Reserves batch identifiers so each process batch is accepted only once."""

    def __init__(self, journal: Journal) -> None:
        self._journal = journal

    def reserve(self, batch_id: str, payload: Mapping[str, Any]) -> None:
        """Publish a batch; a repeated identifier is refused."""
        if self.is_reserved(batch_id):
            raise DuplicateBatchError(f"batch {batch_id} was already accepted")
        row = {"batch_id": batch_id}
        row.update(payload)
        with self._journal.transaction("batch") as batch:
            self._journal.append(keys.batch_key(batch_id), row, batch)

    def payload(self, batch_id: str) -> Mapping[str, Any] | None:
        return self._journal.read(keys.batch_key(batch_id))

    def is_reserved(self, batch_id: str) -> bool:
        return self._journal.has(keys.batch_key(batch_id))

    def release(self, batch_id: str) -> None:
        """Forget a batch identifier so it can be issued again after a cancel."""
        if not self.is_reserved(batch_id):
            raise UnknownBatchError(f"batch {batch_id} was never accepted")
        with self._journal.transaction("batch-release") as batch:
            self._journal.append_tombstone(keys.batch_key(batch_id), batch, "released")

    def reserved_ids(self) -> tuple[str, ...]:
        prefix = keys.BATCH_PREFIX
        return tuple(
            str(self._journal.read(key)["batch_id"]) for key in self._journal.keys(prefix)
        )

    def entries(self) -> tuple[Mapping[str, Any], ...]:
        prefix = keys.BATCH_PREFIX
        return tuple(self._journal.read(key) for key in self._journal.keys(prefix))
