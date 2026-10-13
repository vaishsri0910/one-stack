"""Error types. Every error has a stable machine-readable ``code``."""


class EngineError(Exception):
    code = "ERROR"


class InvalidArgument(EngineError):
    code = "INVALID_ARGUMENT"


class SeatUnavailable(EngineError):
    code = "SEAT_UNAVAILABLE"


class SeatHeld(SeatUnavailable):
    code = "SEAT_HELD"


class SeatSold(SeatUnavailable):
    code = "SEAT_SOLD"


class HoldLimitExceeded(EngineError):
    code = "HOLD_LIMIT_EXCEEDED"


class HoldNotFound(EngineError):
    code = "HOLD_NOT_FOUND"


class HoldReleased(EngineError):
    code = "HOLD_RELEASED"


class HoldLost(EngineError):
    """The seat was taken by someone else after this hold expired."""

    code = "HOLD_LOST"


class AlreadySold(EngineError):
    code = "ALREADY_SOLD"
