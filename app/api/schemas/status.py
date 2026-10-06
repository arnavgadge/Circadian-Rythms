from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.api.schemas.common import BOUNDARY_NOTE


class AlignmentComponents(BaseModel):
    """The five behavioral-alignment components Phase 8 already computes
    and persists (``alignment_results`` columns) -- added here (Phase 16
    compatibility fix) since no earlier phase's API response exposed
    them, even though nothing new is computed to provide them."""

    sleep_consistency: Optional[float] = None
    morning_light: Optional[float] = None
    evening_screen: Optional[float] = None
    meal_timing: Optional[float] = None
    social_jetlag: Optional[float] = None


class AlignmentSummary(BaseModel):
    score: Optional[float] = None
    phase_score: Optional[float] = None
    behavioral_score: Optional[float] = None
    components: Optional[AlignmentComponents] = None
    ideal_sleep_onset: Optional[str] = Field(default=None, description="Estimated ideal sleep onset, HH:MM.")
    actual_sleep_onset: Optional[str] = Field(default=None, description="Most recently observed sleep onset, HH:MM.")


class ConfidenceSummary(BaseModel):
    score: Optional[float] = None
    label: Optional[str] = Field(default=None, description="HIGH | MODERATE | LOW | NO_PREDICTION")
    approximate: bool = Field(description="True when the estimate should be displayed as approximate.")


class ContributorSummary(BaseModel):
    rank: int
    signal: str
    effect_minutes: Optional[float] = Field(default=None, description="Estimated phase effect, minutes. Not a proven cause.")
    alignment_deficit: Optional[float] = None
    contributor_score: Optional[float] = None
    direction: Optional[str] = None
    today_anomaly: Optional[bool] = None


class RecommendationSummary(BaseModel):
    available: bool
    suppressed: bool = False
    intervention_type: Optional[str] = None
    text: Optional[str] = None
    target_display: Optional[str] = None
    expected_improvement_minutes: Optional[float] = None
    expected_improvement_source: Optional[str] = None


class SafetySummary(BaseModel):
    active: bool
    highest_severity: Optional[str] = None
    recommendation_suppressed: bool = False
    flag_types: list = Field(default_factory=list)


class StatusResponse(BaseModel):
    participant_id: int
    prediction_available: bool
    biological_clock: Optional[str] = Field(default=None, description="Estimated biological clock, HH:MM. Not a clinical measurement.")
    chronotype: Optional[str] = None
    approximate: bool = False

    alignment: AlignmentSummary
    confidence: ConfidenceSummary
    contributors: list = Field(default_factory=list, description="Top ranked contributors -- modeled influence, not causes.")
    recommendation: RecommendationSummary
    safety: SafetySummary

    target_date: Optional[str] = None
    boundary_note: str = BOUNDARY_NOTE
    qualifier_message: Optional[str] = None
