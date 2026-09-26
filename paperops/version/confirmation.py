"""Short-lived confirmations bound to a subject and a generation."""

from dataclasses import dataclass
from typing import Any, Mapping

from ..clock import IdSequence, LogicalClock
from ..errors import ConfirmationMismatchError, StaleArtifactError, UnknownConfirmationError
from ..store import Journal, keys
from .generations import Generations


@dataclass(frozen=True)
class Confirmation:
    """An approval that is only valid until a tick and a generation move on."""

    confirmation_id: str
    name: str
    subject: str
    generation: int
    issued_tick: int
    expires_tick: int

    def to_row(self) -> dict[str, Any]:
        return {
            "confirmation_id": self.confirmation_id,
            "name": self.name,
            "subject": self.subject,
            "generation": self.generation,
            "issued_tick": self.issued_tick,
            "expires_tick": self.expires_tick,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Confirmation":
        return cls(
            confirmation_id=str(row["confirmation_id"]),
            name=str(row["name"]),
            subject=str(row["subject"]),
            generation=int(row["generation"]),
            issued_tick=int(row["issued_tick"]),
            expires_tick=int(row["expires_tick"]),
        )


class Confirmations:
    """Issues and redeems confirmations against a logical clock and a generation."""

    def __init__(
        self,
        journal: Journal,
        clock: LogicalClock,
        ids: IdSequence,
        generations: Generations,
    ) -> None:
        self._journal = journal
        self._clock = clock
        self._ids = ids
        self._generations = generations

    def issue(self, name: str, subject: str, ttl_ticks: int) -> Confirmation:
        """Approve a subject for a limited number of ticks at the current generation."""
        if ttl_ticks < 1:
            raise ValueError("ttl_ticks must be at least one tick")
        generation = self._generations.current(name)
        confirmation = Confirmation(
            confirmation_id=self._ids.next(),
            name=name,
            subject=subject,
            generation=generation,
            issued_tick=self._clock.tick,
            expires_tick=self._clock.tick + ttl_ticks,
        )
        with self._journal.transaction("confirmation") as batch:
            self._journal.append(
                keys.confirmation_key(confirmation.confirmation_id),
                confirmation.to_row(),
                batch,
                generation=generation,
            )
        return confirmation

    def get(self, confirmation_id: str) -> Confirmation | None:
        row = self._journal.read(keys.confirmation_key(confirmation_id))
        if row is None:
            return None
        return Confirmation.from_row(row)

    def redeem(self, confirmation_id: str, name: str, subject: str) -> Confirmation:
        """Accept a confirmation only if it still matches its subject and generation."""
        confirmation = self.get(confirmation_id)
        if confirmation is None:
            raise UnknownConfirmationError(f"unknown confirmation {confirmation_id}")
        if confirmation.name != name or confirmation.subject != subject:
            raise ConfirmationMismatchError(
                f"confirmation {confirmation_id} was issued for "
                f"{confirmation.name}/{confirmation.subject}"
            )
        if self.is_expired(confirmation):
            raise StaleArtifactError(
                f"confirmation {confirmation_id} expired at tick {confirmation.expires_tick}"
            )
        self._generations.require_current(
            confirmation.name,
            confirmation.generation,
            f"confirmation {confirmation_id}",
        )
        return confirmation

    def is_expired(self, confirmation: Confirmation) -> bool:
        return self._clock.tick > confirmation.expires_tick

    def outstanding(self) -> tuple[Confirmation, ...]:
        """Confirmations that are still valid at the current tick."""
        prefix = keys.CONFIRMATION_PREFIX
        found = (
            Confirmation.from_row(self._journal.read(key))
            for key in self._journal.keys(prefix)
        )
        return tuple(item for item in found if not self.is_expired(item))
