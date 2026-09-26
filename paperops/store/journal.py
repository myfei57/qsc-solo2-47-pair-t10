"""Append-only record stream with a commit watermark.

Every write lands in the log as an immutable row. A read only ever sees rows at or
below the commit watermark, so a batch that has not committed stays invisible and a
restart replays exactly the committed prefix of the stream.
"""

import json
import os
from contextlib import contextmanager
from typing import Any, Iterator

from ..errors import (
    BatchNotPendingError,
    CommitOrderError,
    DuplicateBatchError,
    MaintenanceError,
    RollbackError,
    UnknownKeyError,
)
from .entry import Entry, EntryKind
from .snapshot import Snapshot
from .view import CommittedView


class Journal:
    """The single source of truth for control state."""

    LOG_NAME = "state.log"
    WATERMARK_NAME = "watermark.json"

    def __init__(self, directory: str | None = None) -> None:
        self._directory = directory
        self._log_path = os.path.join(directory, self.LOG_NAME) if directory else None
        self._watermark_path = (
            os.path.join(directory, self.WATERMARK_NAME) if directory else None
        )
        self._entries: list[Entry] = []
        self._open: dict[str, list[int]] = {}
        self._aborted: set[str] = set()
        self._watermark = 0
        self._read_only = False
        self._batch_counter = 0
        self._committed: dict[str, Entry] = {}
        if directory is not None:
            os.makedirs(directory, exist_ok=True)
            self._load()
        self._batch_counter = len(self._entries)
        self._replay()

    # ------------------------------------------------------------------ writes

    def new_batch(self, prefix: str) -> str:
        """Return a batch identifier that is unused in this stream."""
        while True:
            self._batch_counter += 1
            candidate = f"{prefix}:{self._batch_counter:06d}"
            if candidate not in self._open and candidate not in self._aborted:
                return candidate

    def open(self, batch_id: str) -> None:
        if batch_id in self._open:
            raise DuplicateBatchError(f"batch {batch_id} is already open")
        self._open[batch_id] = []

    def append(self, key: str, value: Any, batch_id: str, generation: int = 0) -> int:
        entry = Entry(
            seq=len(self._entries) + 1,
            kind=EntryKind.PUT,
            key=key,
            batch_id=batch_id,
            generation=generation,
            value=value,
        )
        return self._append(entry, batch_id)

    def append_tombstone(
        self,
        key: str,
        batch_id: str,
        reason: str,
        generation: int = 0,
    ) -> int:
        entry = Entry(
            seq=len(self._entries) + 1,
            kind=EntryKind.TOMBSTONE,
            key=key,
            batch_id=batch_id,
            generation=generation,
            reason=reason,
        )
        return self._append(entry, batch_id)

    def commit(self, batch_id: str) -> int:
        """Publish a batch and move the watermark to the end of the stream so far."""
        self._require_open(batch_id)
        seqs = self._open[batch_id]
        first = min(seqs)
        for other, other_seqs in self._open.items():
            if other != batch_id and min(other_seqs) < first:
                raise CommitOrderError(f"batch {other} is still open below {batch_id}")
        target = max(seqs)
        self._watermark = target
        del self._open[batch_id]
        self._persist_watermark()
        self._replay()
        return target

    def discard(self, batch_id: str) -> int:
        """Drop an uncommitted batch; its rows stay in the log but never publish."""
        self._require_open(batch_id)
        dropped = len(self._open.pop(batch_id))
        self._aborted.add(batch_id)
        self._persist_watermark()
        self._replay()
        return dropped

    def rollback(self, batch_id: str, reason: str = "rolled back") -> int:
        """Undo a committed batch by appending compensating rows to the tail."""
        if batch_id in self._open:
            raise RollbackError(f"batch {batch_id} has not committed yet")
        written = [
            entry
            for entry in self._entries
            if entry.batch_id == batch_id
            and entry.kind is EntryKind.PUT
            and self._visible(entry)
        ]
        if not written:
            raise RollbackError(f"batch {batch_id} has no committed writes")
        low = min(entry.seq for entry in written)
        keys = list(dict.fromkeys(entry.key for entry in written))
        target = self.new_batch("rollback")
        self.open(target)
        for key in reversed(keys):
            prior = self._latest_before(key, low)
            if prior is None:
                self.append_tombstone(key, target, reason)
            else:
                self.append(key, prior.value, target, generation=prior.generation)
        count = len(keys)
        self.commit(target)
        return count

    def set_read_only(self, flag: bool) -> None:
        """Freeze writes, as during planned maintenance."""
        self._read_only = bool(flag)

    @property
    def read_only(self) -> bool:
        return self._read_only

    @contextmanager
    def transaction(self, prefix: str) -> Iterator[str]:
        """Write several keys as one unit; the batch publishes only on clean exit."""
        batch_id = self.new_batch(prefix)
        self.open(batch_id)
        try:
            yield batch_id
        except BaseException:
            self.discard(batch_id)
            raise
        if self._open[batch_id]:
            self.commit(batch_id)
        else:
            del self._open[batch_id]

    # ------------------------------------------------------------------- reads

    def read(self, key: str, default: Any = None) -> Any:
        entry = self._committed.get(key)
        if entry is None:
            return default
        return entry.value

    def require(self, key: str) -> Any:
        entry = self._committed.get(key)
        if entry is None:
            raise UnknownKeyError(f"no committed value for {key}")
        return entry.value

    def has(self, key: str) -> bool:
        return key in self._committed

    def generation_of(self, key: str) -> int:
        entry = self._committed.get(key)
        return entry.generation if entry is not None else 0

    def keys(self, prefix: str = "") -> tuple[str, ...]:
        return tuple(sorted(key for key in self._committed if key.startswith(prefix)))

    def history(self, key: str) -> tuple[Entry, ...]:
        """Every committed row written for a key, in stream order."""
        return tuple(entry for entry in self._entries if entry.key == key and self._visible(entry))

    def entries(self) -> tuple[Entry, ...]:
        return tuple(self._entries)

    def pending_batches(self) -> tuple[str, ...]:
        return tuple(sorted(self._open))

    def aborted_batches(self) -> tuple[str, ...]:
        return tuple(sorted(self._aborted))

    @property
    def watermark(self) -> int:
        return self._watermark

    @property
    def directory(self) -> str | None:
        return self._directory

    @property
    def committed_count(self) -> int:
        return sum(1 for entry in self._entries if self._visible(entry))

    def view(self, watermark: int | None = None) -> CommittedView:
        """Committed rows, optionally frozen at an earlier watermark."""
        limit = self._watermark if watermark is None else watermark
        return CommittedView(self._entries, limit, self._aborted)

    def snapshot(self) -> Snapshot:
        view = self.view()
        return Snapshot(watermark=view.watermark, digest=view.digest(), keys=view.keys())

    # ---------------------------------------------------------------- internals

    def _append(self, entry: Entry, batch_id: str) -> int:
        if self._read_only:
            raise MaintenanceError("store is in maintenance mode")
        if batch_id not in self._open:
            raise BatchNotPendingError(f"batch {batch_id} is not open")
        self._entries.append(entry)
        self._open[batch_id].append(entry.seq)
        self._write(entry)
        return entry.seq

    def _require_open(self, batch_id: str) -> None:
        if batch_id not in self._open:
            raise BatchNotPendingError(f"batch {batch_id} is not open")

    def _visible(self, entry: Entry) -> bool:
        return entry.seq <= self._watermark and entry.batch_id not in self._aborted

    def _latest_before(self, key: str, seq: int) -> Entry | None:
        latest: Entry | None = None
        for entry in self._entries:
            if entry.key != key or entry.seq >= seq or not self._visible(entry):
                continue
            latest = entry if entry.kind is EntryKind.PUT else None
        return latest

    def _replay(self) -> None:
        self._committed = {}
        for entry in self._entries:
            if not self._visible(entry):
                continue
            if entry.kind is EntryKind.TOMBSTONE:
                self._committed.pop(entry.key, None)
            else:
                self._committed[entry.key] = entry

    def _write(self, entry: Entry) -> None:
        if self._log_path is None:
            return
        with open(self._log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry.to_row(), sort_keys=True, ensure_ascii=True))
            handle.write("\n")

    def _persist_watermark(self) -> None:
        if self._watermark_path is None:
            return
        payload = {"watermark": self._watermark, "aborted": sorted(self._aborted)}
        with open(self._watermark_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)

    def _load(self) -> None:
        if self._log_path and os.path.exists(self._log_path):
            with open(self._log_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if line:
                        self._entries.append(Entry.from_row(json.loads(line)))
        if self._watermark_path and os.path.exists(self._watermark_path):
            with open(self._watermark_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            self._watermark = int(payload.get("watermark", 0))
            self._aborted = set(payload.get("aborted", []))
        for entry in self._entries:
            if entry.seq > self._watermark and entry.batch_id not in self._aborted:
                self._open.setdefault(entry.batch_id, []).append(entry.seq)
