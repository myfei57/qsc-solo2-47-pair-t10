"""Exceptions raised when a control contract is violated."""


class ContractError(Exception):
    """Base class for every contract violation raised by the service."""


class UnknownKeyError(ContractError):
    """Raised when a committed value is required but the key has no committed row."""


class MaintenanceError(ContractError):
    """Raised when a write is attempted while the store is in maintenance mode."""


class BatchNotPendingError(ContractError):
    """Raised when a batch is committed, discarded or rolled back while not open."""


class DuplicateBatchError(ContractError):
    """Raised when a batch identifier is opened twice or reserved twice."""


class CommitOrderError(ContractError):
    """Raised when a commit would carry the watermark past an earlier open batch."""


class RollbackError(ContractError):
    """Raised when a rollback target is not a committed batch."""


class UnknownBatchError(ContractError):
    """Raised when a reserved batch identifier is released but was never reserved."""


class StaleArtifactError(ContractError):
    """Raised when a confirmation, snapshot or baseline has expired."""


class UnknownConfirmationError(ContractError):
    """Raised when a confirmation identifier cannot be found."""


class ConfirmationMismatchError(ContractError):
    """Raised when a confirmation is redeemed for a different subject or generation."""


class UnknownStageError(ContractError):
    """Raised when a stage is used that the procedure does not declare."""


class OutOfSequenceError(ContractError):
    """Raised when a stage is opened before its predecessors closed."""


class DuplicateStageError(ContractError):
    """Raised when a stage that already closed is opened again."""


class LatchSetError(ContractError):
    """Raised when a latch is set while one of its set conditions is unmet."""


class LatchClearError(ContractError):
    """Raised when a latch is cleared while one of its clear conditions is unmet."""


class PreGateError(ContractError):
    """Raised when a downstream action runs before its upstream value is durable."""


class OutOfRangeError(ContractError):
    """Raised when a parameter falls outside its declared band."""


class UnknownSensorError(ContractError):
    """Raised when a moisture sensor is addressed before it is mapped."""
