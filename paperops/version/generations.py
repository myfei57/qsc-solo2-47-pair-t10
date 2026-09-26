"""Generation numbers for parameters and configuration.

A parameter set carries a generation. Anything derived from a parameter set records
the generation it was derived from, so a superseded derivation can be refused.
"""

from ..errors import StaleArtifactError
from ..store import Journal, keys


class Generations:
    """Generation counter kept per parameter name in the record stream."""

    def __init__(self, journal: Journal) -> None:
        self._journal = journal

    def current(self, name: str) -> int:
        """Generation in force for a parameter name; zero when never issued."""
        return int(self._journal.read(keys.version_key(name), 0) or 0)

    def is_current(self, name: str, generation: int) -> bool:
        return self.current(name) == generation

    def advance(self, name: str, prefix: str) -> int:
        """Publish the next generation for a parameter name."""
        generation = self.current(name) + 1
        with self._journal.transaction(prefix) as batch:
            self._journal.append(
                keys.version_key(name),
                generation,
                batch,
                generation=generation,
            )
        return generation

    def require_current(self, name: str, generation: int, artifact: str) -> None:
        current = self.current(name)
        if not self.is_current(name, generation):
            raise StaleArtifactError(
                f"{artifact} carries generation {generation} but {name} is at {current}"
            )

    def all(self) -> dict[str, int]:
        prefix = keys.VERSION_PREFIX
        return {
            key[len(prefix) :]: int(self._journal.read(key, 0) or 0)
            for key in self._journal.keys(prefix)
        }
