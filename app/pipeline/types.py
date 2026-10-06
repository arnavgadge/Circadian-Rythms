"""Result and status types for the daily inference pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_cls
from typing import Optional

SUCCESS = "SUCCESS"
INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
NO_PREDICTION = "NO_PREDICTION"
FAILED = "FAILED"
ALREADY_COMPUTED = "ALREADY_COMPUTED"

STATUSES = (SUCCESS, INSUFFICIENT_HISTORY, NO_PREDICTION, FAILED, ALREADY_COMPUTED)


@dataclass(frozen=True)
class ParticipantStateUpdate:
    """The Phase 11-owned mutation of ``ParticipantProfile``'s current
    state -- kept structurally distinct from the immutable historical
    ``CircadianLabel`` row (see docs "Current vs. historical state")."""

    previous_current_dlmo_hour: Optional[float]
    new_current_dlmo_hour: Optional[float]
    previous_adapted_dlmo_hour: Optional[float]
    new_adapted_dlmo_hour: Optional[float]
    intrinsic_dlmo_hour_unchanged: float
    new_alignment_score: Optional[float]
    applied: bool


@dataclass(frozen=True)
class DailyInferenceResult:
    participant_id: int
    target_date: date_cls
    status: str
    failure_stage: Optional[str] = None
    failure_message: Optional[str] = None

    history_days_available: int = 0

    feature_metadata: Optional[dict] = None

    xgb_prediction: Optional[dict] = None
    state_prediction: Optional[dict] = None
    fusion_result: Optional[object] = None

    alignment_result: Optional[object] = None
    contributor_result: Optional[object] = None
    recommendation_result: Optional[object] = None

    participant_state_update: Optional[ParticipantStateUpdate] = None

    persistence_status: str = "not_attempted"  # "not_attempted" | "committed" | "rolled_back" | "skipped"
    circadian_label_id: Optional[int] = None
    idempotent_short_circuit: bool = False

    runtime_seconds: Optional[float] = None
    diagnostics: dict = field(default_factory=dict)
