from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class InterventionHistoryEntry(BaseModel):
    intervention_log_id: int
    intervention_code: str
    intervention_type: str
    log_date: date_type
    target_display: Optional[str] = None
    actual_display: Optional[str] = None
    compliance_degree: Optional[float] = None
    compliance_binary: Optional[bool] = None
    observation_status: str = Field(description="observed | missing")
    measurement_phase: Optional[int] = None
    effect_estimate: Optional[float] = None


class InterventionHistoryResponse(BaseModel):
    participant_id: int
    entries: list
    count: int


class OutcomeSubmissionRequest(BaseModel):
    observation_date: date_type
    actual_value_time: Optional[str] = Field(default=None, description="HH:MM (24h), for clock-time interventions.")
    actual_value_numeric: Optional[float] = Field(default=None, description="For duration/magnitude interventions.")
    observed: bool = Field(default=True, description="False if the participant explicitly reports no data for this day.")

    @field_validator("actual_value_time")
    @classmethod
    def _validate_time_format(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        parts = value.split(":")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            raise ValueError("actual_value_time must be in HH:MM format")
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError("actual_value_time must be a valid 24h clock time")
        return value

    @field_validator("actual_value_numeric")
    @classmethod
    def _validate_numeric_bounds(cls, value: Optional[float]) -> Optional[float]:
        if value is None:
            return value
        if not (-1000.0 <= value <= 1000.0):
            raise ValueError("actual_value_numeric out of plausible bounds")
        return value


class OutcomeSubmissionResponse(BaseModel):
    intervention_log_id: int
    observation_date: date_type
    compliance_degree: Optional[float] = None
    compliance_binary: Optional[bool] = None
    applied: bool
