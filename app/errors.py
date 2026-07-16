class ModelNotConfiguredError(RuntimeError):
    """Raised when an operation requires missing model credentials."""


class NotFoundError(RuntimeError):
    """Raised when a requested resource does not exist."""

