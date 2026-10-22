class LivewireError(Exception):
    """Base class of all errors raised by this library."""


class AuthenticationError(LivewireError):
    """Logging in failed."""


class ApiError(LivewireError):
    """The backend answered with an error, as HTTP status or as error envelope."""

    def __init__(
        self, message: str, *, code: str | None = None, status: int | None = None
    ):
        super().__init__(message)
        self.code = code
        self.status = status


class NotPairedError(ApiError):
    """The bike did not answer for this device UUID (error code 3000).

    The backend reports this when the device UUID is not paired with the bike,
    and also when it cannot reach the bike at all.
    """


class PairingError(LivewireError):
    """Requesting or verifying a pairing code failed."""

    def __init__(self, message: str, *, code: int | None = None):
        super().__init__(message)
        self.code = code
