"""Snapshots and baselines recorded together with the generation they came from."""

from dataclasses import dataclass
from typing import Any, Mapping

from ..clock import LogicalClock
from ..errors import StaleArtifactError
from ..store import Journal, keys
from .generations import Generations


@dataclass(frozen=True)
class ArtifactRef:
    """A derived value pinned to the generation and tick that produced it."""

    kind: str
    name: str
    generation: int
    tick: int
    digest: str

    def to_row(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "generation": self.generation,
            "tick": self.tick,
            "digest": self.digest,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "ArtifactRef":
        return cls(
            kind=str(row["kind"]),
            name=str(row["name"]),
            generation=int(row["generation"]),
            tick=int(row["tick"]),
            digest=str(row["digest"]),
        )


class Artifacts:
    """Keeps the latest snapshot and baseline of each name and refuses stale ones."""

    def __init__(self, journal: Journal, clock: LogicalClock) -> None:
        self._journal = journal
        self._clock = clock

    def record(self, kind: str, name: str, generation: int, digest: str) -> ArtifactRef:
        ref = ArtifactRef(
            kind=kind,
            name=name,
            generation=generation,
            tick=self._clock.tick,
            digest=digest,
        )
        with self._journal.transaction(f"artifact-{kind}") as batch:
            self._journal.append(
                keys.artifact_key(kind, name),
                ref.to_row(),
                batch,
                generation=generation,
            )
        return ref

    def get(self, kind: str, name: str) -> ArtifactRef | None:
        row = self._journal.read(keys.artifact_key(kind, name))
        if row is None:
            return None
        return ArtifactRef.from_row(row)

    def require_current(
        self,
        kind: str,
        name: str,
        max_age_ticks: int,
        generations: Generations,
    ) -> ArtifactRef:
        """Refuse an artifact that has been superseded or has aged past its limit."""
        ref = self.get(kind, name)
        if ref is None:
            raise StaleArtifactError(f"no {kind} recorded as {name}")
        generations.require_current(ref.name, ref.generation, f"{kind} {name}")
        age = self._clock.tick - ref.tick
        if age > max_age_ticks:
            raise StaleArtifactError(
                f"{kind} {name} is {age} ticks old, limit is {max_age_ticks}"
            )
        return ref

    def age(self, kind: str, name: str) -> int:
        ref = self.get(kind, name)
        if ref is None:
            raise StaleArtifactError(f"no {kind} recorded as {name}")
        return self._clock.tick - ref.tick

    def stale(
        self,
        kind: str,
        name: str,
        max_age_ticks: int,
        generations: Generations,
    ) -> bool:
        try:
            self.require_current(kind, name, max_age_ticks, generations)
        except StaleArtifactError:
            return True
        return False
