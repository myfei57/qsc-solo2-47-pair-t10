"""Append-only event record stream, replayed on restart."""

import json
import os
from pathlib import Path
from typing import Any

from ..clock import IdSequence, parse_id
from .record import AuditRecord


class AuditLog:
    """Keeps every control event in the order it happened."""

    LOG_NAME = "audit.log"

    def __init__(self, directory: str | None = None) -> None:
        self._records: list[AuditRecord] = []
        self._ids = IdSequence("evt")
        self._seq = 0
        self._path = os.path.join(directory, self.LOG_NAME) if directory else None
        if directory is not None:
            os.makedirs(directory, exist_ok=True)
            self._load()

    def append(
        self,
        topic: str,
        payload: Any,
        tick: int,
        generation: int = 0,
        batch_id: str = "",
    ) -> AuditRecord:
        self._seq += 1
        record = AuditRecord(
            seq=self._seq,
            record_id=self._ids.next(),
            topic=topic,
            tick=int(tick),
            generation=int(generation),
            batch_id=batch_id,
            payload=payload,
        )
        self._records.append(record)
        self._write(record)
        return record

    def records(self) -> tuple[AuditRecord, ...]:
        return tuple(self._records)

    def count(self, topic: str) -> int:
        return sum(1 for record in self._records if record.topic == topic)

    @property
    def sequence(self) -> int:
        return self._seq

    def clear(self) -> int:
        """Empty the stream while keeping the sequence running."""
        cleared = len(self._records)
        self._records = []
        if self._path is not None:
            Path(self._path).write_text("", encoding="utf-8")
        return cleared

    def _write(self, record: AuditRecord) -> None:
        if self._path is None:
            return
        with open(self._path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_row(), sort_keys=True, ensure_ascii=True))
            handle.write("\n")

    def _load(self) -> None:
        if self._path is None or not os.path.exists(self._path):
            return
        with open(self._path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = AuditRecord.from_row(json.loads(line))
                self._records.append(record)
                self._seq = max(self._seq, record.seq)
                issued = parse_id(record.record_id)
                if issued is not None:
                    self._ids.restore(issued)
