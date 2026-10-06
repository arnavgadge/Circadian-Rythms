from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class OnboardingRequest(BaseModel):
    participant_code: str = Field(min_length=1, max_length=50)
    enrollment_date: Optional[date_type] = None
    chronotype: Optional[str] = Field(default=None, description="Intermediate | Early | Late, if already known.")
    meq_score: Optional[float] = Field(default=None, ge=0, le=100)
    msfsc_time: Optional[str] = Field(default=None, description="Mid-sleep on free days, corrected. HH:MM (24h).")

    @field_validator("msfsc_time")
    @classmethod
    def _validate_time(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        parts = value.split(":")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            raise ValueError("msfsc_time must be in HH:MM format")
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError("msfsc_time must be a valid 24h clock time")
        return value


class OnboardingResponse(BaseModel):
    participant_id: int
    participant_code: str
    status: str
    note: str = (
        "Onboarding records the participant and any supplied questionnaire baseline. "
        "This prototype does not compute an initial estimated biological clock from "
        "questionnaire data alone -- a prediction becomes available once enough daily "
        "behavioral history has been logged and daily inference has run."
    )
