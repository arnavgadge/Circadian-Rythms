"""Application service for the safety-status endpoint. Read-only --
never re-runs pattern detection (that only happens as part of
``POST /inference``, see ``InferenceService``)."""

from __future__ import annotations

from app.api.repositories.circadian_repository import CircadianRepository
from app.api.repositories.safety_repository import SafetyRepository
from app.api.schemas.safety import SafetyFlagEntry, SafetyStatusResponse
from app.safety.enums import HIGH


class SafetyService:
    def __init__(self, safety_repository: SafetyRepository, circadian_repository: CircadianRepository):
        self.safety_repository = safety_repository
        self.circadian_repository = circadian_repository

    def get_status(self, participant_id: int) -> SafetyStatusResponse:
        active_flags = self.safety_repository.get_active_flags(participant_id)
        latest_label = self.circadian_repository.get_latest(participant_id)

        highest_severity = (latest_label.safety_severity if latest_label else None) or (
            HIGH if any(f.severity == HIGH for f in active_flags) else ("MODERATE" if active_flags else None)
        )
        recommendation_suppressed = (
            latest_label.recommendation_suppressed if latest_label and latest_label.recommendation_suppressed is not None else (highest_severity == HIGH)
        )
        prediction_available = bool(latest_label and latest_label.fused_dlmo_time is not None and latest_label.confidence_label != "no_prediction")

        return SafetyStatusResponse(
            participant_id=participant_id,
            active_flags=[
                SafetyFlagEntry(
                    flag_type=f.flag_type, severity=f.severity, message_key=f.message_key,
                    first_detected_date=f.first_detected_date, last_observed_date=f.last_observed_date,
                )
                for f in active_flags
            ],
            highest_severity=highest_severity,
            prediction_available=prediction_available,
            recommendation_suppressed=bool(recommendation_suppressed),
        )
