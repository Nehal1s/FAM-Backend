class DbTimeoutError(Exception):
    """Database query exceeded configured timeout."""


class DbPoolExhaustedError(Exception):
    """Could not acquire a connection from the pool in time."""
