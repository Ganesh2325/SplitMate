"""Domain errors that are safe to show to a user."""


class SplitMateError(Exception):
    """Base class for expected application errors."""


class DomainError(SplitMateError):
    def __init__(self, message, field=None):
        self.field = field
        super().__init__(message)


class AuthorizationError(SplitMateError):
    """The caller cannot perform the operation. Views turn this into a 404."""
