"""Moisture sensing, the sensor map and the cross direction profile.

The sensor map is a parameter set with a generation. Sampling by sensor name resolves
the position through the map, and rebuilding the map drops the cached profile, so a
profile computed against an old map can never be served after a scanner change.
"""

from typing import Any, Mapping, Sequence

from ..clock import LogicalClock
from ..errors import OutOfRangeError, UnknownSensorError
from ..event import Event, EventBus, topics
from ..store import Journal, keys
from ..verdict import Band, VerdictHistory, Window, WindowEvaluator
from ..verdict import ABOVE_MODE
from ..version import Confirmations, Generations
from . import calc
from .view import WaterView

MAP_NAME = "water.map"
WATER_NAME = "water"
SAMPLE_LIMIT = 60
MOISTURE_BAND = Band(2.0, 12.0)
WINDOW_SIZE = 3


class WaterService:
    """Sensor map, moisture samples and the cross direction profile."""

    def __init__(
        self,
        journal: Journal,
        bus: EventBus,
        clock: LogicalClock,
        generations: Generations,
        confirmations: Confirmations,
    ) -> None:
        self._journal = journal
        self._bus = bus
        self._clock = clock
        self._generations = generations
        self._confirmations = confirmations
        self._band = MOISTURE_BAND
        self._history = VerdictHistory("water.moisture")
        self._sustained = WindowEvaluator(Window(WINDOW_SIZE), 12.0, ABOVE_MODE, WINDOW_SIZE)
        self._sensors = calc.default_sensors()
        self._profile_cache: list[dict[str, float]] | None = None

    # ----------------------------------------------------------------- reading

    def map_sensors(self) -> dict[str, float]:
        return dict(self._sensors)

    def generation(self) -> int:
        row = self._journal.read(keys.WATER_MAP)
        if row is None:
            return 0
        return int(row["generation"])

    def samples(self) -> tuple[dict[str, Any], ...]:
        rows = self._journal.read(keys.WATER_SAMPLES)
        if rows is None:
            return ()
        return tuple(rows)

    def values(self) -> tuple[float, ...]:
        return tuple(float(row["moisture"]) for row in self.samples())

    def average(self) -> float:
        return calc.average(self.values())

    def span(self) -> float:
        return calc.span(self.values())

    def edge_center(self) -> float:
        edges = [
            float(row["moisture"])
            for row in self.samples()
            if row["name"] in ("front", "back")
        ]
        center = next(
            (float(row["moisture"]) for row in self.samples() if row["name"] == "middle"),
            0.0,
        )
        if not edges:
            edges = list(self.values())
        return calc.edge_center(edges, center)

    def history(self) -> VerdictHistory:
        return self._history

    def profile(self) -> list[dict[str, float]]:
        """Cross direction profile, computed once and reused until the map moves."""
        if self._profile_cache is not None:
            return [dict(point) for point in self._profile_cache]
        points = sorted(
            (float(row["position"]), float(row["moisture"]))
            for row in self.samples()
        )
        self._profile_cache = [
            {"position": position, "moisture": moisture} for position, moisture in points
        ]
        return [dict(point) for point in self._profile_cache]

    def at(self, position: float) -> float:
        """Interpolated moisture at a cross direction position."""
        points = [
            (float(row["position"]), float(row["moisture"])) for row in self.samples()
        ]
        return calc.interpolate(points, position)

    def moisture(self) -> float:
        return self.average()

    def moisture_verdict(self, reading: float) -> str:
        result = calc.verdict(reading, self._band.low, self._band.high)
        self._history.record(
            result,
            self._journal.watermark,
            self._clock.tick,
            f"reading={reading}",
        )
        return result

    def sustained_dry(self, reading: float):
        """Verdict that only holds once a whole window of readings is above target."""
        return self._sustained.push(reading)

    def view(self) -> WaterView:
        return WaterView(
            sensors=self.map_sensors(),
            samples=len(self.samples()),
            average=self.average(),
            span=self.span(),
            edge_center=self.edge_center(),
            generation=self.generation(),
        )

    # ------------------------------------------------------------------ writes

    def rebuild_map(self, sensors: Mapping[str, float], confirmation_id: str) -> dict[str, Any]:
        """Replace the sensor map under a confirmation and a new generation."""
        checked = calc.validate_sensors(sensors)
        self._confirmations.redeem(confirmation_id, MAP_NAME, WATER_NAME)
        generation = self._generations.advance(MAP_NAME, "water-map-generation")
        tick = self._clock.tick
        row = {"sensors": checked, "generation": generation, "tick": tick}
        with self._journal.transaction("water-map") as batch:
            self._journal.append(keys.WATER_MAP, row, batch, generation=generation)
        self._sensors = dict(checked)
        self._profile_cache = None
        self._bus.publish(topics.TOPIC_WATER_MAP, generation)
        return dict(row)

    def replace_scanner(self) -> int:
        """Move the generation on so a profile built on the old map is refused."""
        generation = self._generations.advance(MAP_NAME, "water-scanner")
        self._profile_cache = None
        self._bus.publish(topics.TOPIC_WATER_MAP, generation)
        return generation

    def add_sample(self, name: str, moisture: float) -> dict[str, Any]:
        """Sample a named sensor; the name has to exist in the current map."""
        if name not in self._sensors:
            raise UnknownSensorError(f"sensor {name} is not mapped")
        return self.add_reading(name, self._sensors[name], moisture)

    def add_reading(self, name: str, position: float, moisture: float) -> dict[str, Any]:
        """Record a moisture reading at a known cross direction position."""
        self._band.require(moisture, "moisture reading")
        rows = list(self.samples())
        rows.append(
            {
                "name": name,
                "position": float(position),
                "moisture": float(moisture),
                "tick": self._clock.tick,
            }
        )
        rows = rows[-SAMPLE_LIMIT:]
        with self._journal.transaction("water-sample") as batch:
            self._journal.append(keys.WATER_SAMPLES, rows, batch)
        self._profile_cache = None
        self._bus.publish(topics.TOPIC_WATER_SAMPLE, name)
        return {"name": name, "position": float(position), "moisture": float(moisture)}

    def record_profile(self) -> dict[str, Any]:
        """Freeze the current profile as a recorded curve."""
        points = self.profile()
        row = {
            "points": points,
            "average": self.average(),
            "span": self.span(),
            "tick": self._clock.tick,
        }
        with self._journal.transaction("water-profile") as batch:
            self._journal.append(keys.WATER_PROFILE, row, batch)
        self._bus.publish(topics.TOPIC_WATER_PROFILE, len(points))
        return dict(row)

    def reload(self) -> WaterView:
        stored = self._journal.read(keys.WATER_MAP)
        if stored is not None:
            self._sensors = {str(k): float(v) for k, v in stored["sensors"].items()}
        self._profile_cache = None
        return self.view()

    def wire(self) -> None:
        """Drop the cached profile whenever the sensor map moves."""
        self._bus.subscribe(topics.TOPIC_WATER_MAP, self._on_map_change)

    # -------------------------------------------------------------- arithmetic

    def average_of(self, readings: Sequence[float]) -> float:
        return calc.average(readings)

    def span_of(self, readings: Sequence[float]) -> float:
        return calc.span(readings)

    def deviation(self, reading: float) -> float:
        return float(reading) - self.average()

    def verdict_of(self, reading: float) -> str:
        return calc.verdict(reading, self._band.low, self._band.high)

    def verify_band(self, value: float, label: str) -> float:
        return self._band.require(value, label)

    def negative(self, value: float, label: str) -> float:
        if value < 0:
            raise OutOfRangeError(f"{label} must not be negative")
        return float(value)

    # ---------------------------------------------------------------- internals

    def _on_map_change(self, event: Event) -> None:
        self._profile_cache = None
