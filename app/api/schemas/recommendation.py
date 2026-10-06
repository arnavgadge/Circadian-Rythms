from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class PrimaryRecommendation(BaseModel):
    intervention_type: str
    text: str
    target_display: Optional[str] = None
    expected_improvement_minutes: Optional[float] = None
    expected_improvement_source: Optional[str] = Field(default=None, description="literature | personal | blended")


class RecommendationResponse(BaseModel):
    participant_id: int
    available: bool
    suppressed: bool = False
    primary: Optional[PrimaryRecommendation] = None
    supporting: list = Field(
        default_factory=list,
        description="Supporting nudges are not currently persisted by the daily pipeline; only the primary recommendation is available via read endpoints.",
    )
    personalization_phase: Optional[str] = None
    safety_message: Optional[str] = Field(default=None, description="Shown instead of a behavioral recommendation when suppressed.")
    non_diagnostic_statement: Optional[str] = None
