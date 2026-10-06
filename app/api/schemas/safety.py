from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from pydantic import BaseModel, Field

from app.api.schemas.common import BOUNDARY_NOTE


class SafetyFlagEntry(BaseModel):
    flag_type: str
    severity: str
    message_key: Optional[str] = None
    first_detected_date: Optional[date_type] = None
    last_observed_date: Optional[date_type] = None


class SafetyStatusResponse(BaseModel):
    participant_id: int
    active_flags: list = Field(default_factory=list)
    highest_severity: Optional[str] = None
    prediction_available: bool
    recommendation_suppressed: bool
    non_diagnostic_message_key: Optional[str] = "NON_DIAGNOSTIC_STATEMENT"
    boundary_note: str = BOUNDARY_NOTE
