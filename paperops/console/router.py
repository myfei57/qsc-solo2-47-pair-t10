"""Request routing for the control console."""

from typing import Any, Callable

from ..errors import (
    BatchNotPendingError,
    CommitOrderError,
    ConfirmationMismatchError,
    ContractError,
    DuplicateBatchError,
    DuplicateStageError,
    LatchClearError,
    LatchSetError,
    MaintenanceError,
    OutOfRangeError,
    OutOfSequenceError,
    PreGateError,
    RollbackError,
    StaleArtifactError,
    UnknownBatchError,
    UnknownConfirmationError,
    UnknownKeyError,
    UnknownSensorError,
    UnknownStageError,
)
from . import handlers, operations
from .http import Request, Response, error_response
from .pages import page_names

Handler = Callable[["Console", Request], Response]

CONFLICT = (
    PreGateError,
    LatchSetError,
    LatchClearError,
    OutOfSequenceError,
    DuplicateStageError,
    DuplicateBatchError,
    StaleArtifactError,
    RollbackError,
    CommitOrderError,
)
MALFORMED = (OutOfRangeError, UnknownStageError, ConfirmationMismatchError)
MISSING = (
    UnknownKeyError,
    UnknownConfirmationError,
    UnknownBatchError,
    BatchNotPendingError,
    UnknownSensorError,
)

ROUTES: tuple[tuple[str, str, Handler], ...] = (
    ("GET", "/healthz", handlers.health),
    ("GET", "/api/state", handlers.state),
    ("GET", "/api/state/counters", handlers.counters),
    ("GET", "/api/state/routes", handlers.routes),
    ("GET", "/api/state/histories", handlers.histories),
    ("GET", "/api/state/snapshot", handlers.snapshot_status),
    ("GET", "/api/state/artifacts", handlers.artifacts_status),
    ("POST", "/api/state/snapshot", operations.state_snapshot),
    ("GET", "/api/verdict/history", handlers.verdict_history),
    ("GET", "/api/confirmations", handlers.confirmations),
    ("GET", "/api/batches", handlers.batches),
    ("POST", "/api/batch/release", operations.batch_release),
    ("GET", "/api/journal/keys", handlers.journal_keys),
    ("GET", "/api/journal/entries", handlers.journal_entries),
    ("GET", "/api/journal/pending", handlers.journal_pending),
    ("GET", "/api/journal/view", handlers.journal_view),
    ("GET", "/api/journal/stats", handlers.journal_stats),
    ("POST", "/api/journal/commit", operations.journal_commit),
    ("POST", "/api/journal/discard", operations.journal_discard),
    ("POST", "/api/journal/rollback", operations.journal_rollback),
    ("POST", "/api/journal/maintenance", operations.journal_maintenance),
    ("POST", "/api/clock/advance", operations.journal_advance_tick),
    ("POST", "/api/confirmation", operations.confirmation_issue),
    ("GET", "/api/audit", handlers.audit),
    ("GET", "/api/audit/summary", handlers.audit_summary),
    ("POST", "/api/audit/clear", operations.audit_clear),
    ("GET", "/api/press/state", handlers.press_state),
    ("GET", "/api/press/model", handlers.press_model),
    ("POST", "/api/press/load", operations.press_load),
    ("POST", "/api/press/dewater", operations.press_dewater),
    ("POST", "/api/press/persist", operations.press_persist),
    ("POST", "/api/press/gain", operations.press_gain),
    ("GET", "/api/dry/state", handlers.dry_state),
    ("GET", "/api/dry/procedure", handlers.dry_procedure),
    ("GET", "/api/dry/model", handlers.dry_model),
    ("POST", "/api/dry/begin", operations.dry_begin),
    ("POST", "/api/dry/drain", operations.dry_drain),
    ("POST", "/api/dry/admit", operations.dry_admit),
    ("POST", "/api/dry/warm", operations.dry_warm),
    ("POST", "/api/dry/run", operations.dry_run),
    ("POST", "/api/dry/heat", operations.dry_heat),
    ("POST", "/api/dry/speed", operations.dry_speed),
    ("POST", "/api/dry/curve", operations.dry_curve),
    ("GET", "/api/steam/state", handlers.steam_state),
    ("GET", "/api/steam/pressure", handlers.steam_pressure),
    ("GET", "/api/steam/model", handlers.steam_model),
    ("POST", "/api/steam/drain", operations.steam_drain),
    ("POST", "/api/steam/valve", operations.steam_valve),
    ("POST", "/api/steam/stop", operations.steam_stop),
    ("POST", "/api/steam/calibrate", operations.steam_calibrate),
    ("POST", "/api/steam/gauge", operations.steam_gauge),
    ("GET", "/api/glue/state", handlers.glue_state),
    ("GET", "/api/glue/model", handlers.glue_model),
    ("POST", "/api/glue/roll", operations.glue_roll),
    ("POST", "/api/glue/pump", operations.glue_pump),
    ("POST", "/api/glue/stop", operations.glue_stop),
    ("POST", "/api/glue/alarm", operations.glue_alarm),
    ("POST", "/api/glue/concentration", operations.glue_concentration),
    ("GET", "/api/cal/state", handlers.cal_state),
    ("GET", "/api/cal/model", handlers.cal_model),
    ("POST", "/api/cal/speed", operations.cal_speed),
    ("POST", "/api/cal/nip", operations.cal_nip),
    ("GET", "/api/reel/state", handlers.reel_state),
    ("GET", "/api/reel/geometry", handlers.reel_geometry),
    ("POST", "/api/reel/change", operations.reel_change),
    ("POST", "/api/reel/spool", operations.reel_spool),
    ("POST", "/api/reel/retract", operations.reel_retract),
    ("POST", "/api/reel/bite", operations.reel_bite),
    ("POST", "/api/reel/break", operations.reel_break),
    ("GET", "/api/broke/state", handlers.broke_state),
    ("GET", "/api/broke/model", handlers.broke_model),
    ("POST", "/api/broke/trip", operations.broke_trip),
    ("POST", "/api/broke/process", operations.broke_process),
    ("POST", "/api/broke/reset", operations.broke_reset),
    ("POST", "/api/broke/takeover", operations.broke_takeover),
    ("GET", "/api/water/state", handlers.water_state),
    ("GET", "/api/water/profile", handlers.water_profile),
    ("GET", "/api/water/verdict", handlers.water_verdict),
    ("GET", "/api/water/model", handlers.water_model),
    ("POST", "/api/water/map", operations.water_map),
    ("POST", "/api/water/scanner", operations.water_scanner),
    ("POST", "/api/water/sample", operations.water_sample),
    ("POST", "/api/water/reading", operations.water_reading),
    ("POST", "/api/water/profile", operations.water_profile),
) + ((("GET", "/", handlers.page),) + tuple(
    ("GET", "/" + name, handlers.page) for name in page_names()
))


def status_for(error: ContractError) -> int:
    """Map a contract violation onto a response status."""
    if isinstance(error, CONFLICT):
        return 409
    if isinstance(error, MALFORMED):
        return 422
    if isinstance(error, MISSING):
        return 404
    if isinstance(error, MaintenanceError):
        return 503
    return 400


class Console:
    """Routes requests onto subsystem operations and renders the status pages."""

    def __init__(self, services: Any) -> None:
        self.services = services
        self._routes: dict[tuple[str, str], Handler] = {
            (method, path): handler for method, path, handler in ROUTES
        }

    def routes(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(self._routes))

    def handle(self, request: Request) -> Response:
        handler = self._routes.get((request.method, request.path))
        if handler is None:
            return error_response(
                f"no route for {request.method} {request.path}",
                status=404,
            )
        try:
            return handler(self, request)
        except ContractError as error:
            return error_response(str(error), status=status_for(error))
        except (KeyError, ValueError, TypeError) as error:
            return error_response(f"malformed request: {error}", status=400)
