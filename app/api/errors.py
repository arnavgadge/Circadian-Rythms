"""Centralized application-layer error types and their HTTP mapping.

Routes/services raise these; nothing downstream of a service ever
constructs a raw ``HTTPException`` directly (see ``app.api.main`` for
the exception handlers that perform the actual translation) -- one
place decides what a client sees, so a stack trace or database detail
can never leak through a route by accident.
"""

from __future__ import annotations


class ApplicationError(Exception):
    """Base class for every error the service layer raises."""

    status_code = 500

    def __init__(self, message: str, *, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail


class NotFoundError(ApplicationError):
    status_code = 404


class ValidationFailedError(ApplicationError):
    status_code = 400


class ConflictError(ApplicationError):
    status_code = 409


class DependencyUnavailableError(ApplicationError):
    status_code = 503
