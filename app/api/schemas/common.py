"""Shared response primitives. ``BOUNDARY_NOTE`` is imported directly
from ``app.safety.messages`` (never duplicated) so the API can never
drift from the one authoritative wording of the wellness boundary.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.safety.messages import BOUNDARY_NOTE_SHORT

BOUNDARY_NOTE = BOUNDARY_NOTE_SHORT


class ErrorResponse(BaseModel):
    """The one error shape every non-2xx response uses."""

    error: str = Field(description="Machine-readable error code, e.g. 'not_found'.")
    message: str = Field(description="Human-readable summary safe to display.")
    detail: Optional[str] = Field(default=None, description="Additional context, if any.")
    correlation_id: Optional[str] = Field(default=None, description="Request correlation ID for support/debugging.")
