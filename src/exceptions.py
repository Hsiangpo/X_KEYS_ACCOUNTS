"""Custom exceptions for crawler flows."""


class AuthenticationError(RuntimeError):
    """Raised when X API rejects the current session."""


class ProtocolRequestError(RuntimeError):
    """Raised when protocol requests fail after retries."""

