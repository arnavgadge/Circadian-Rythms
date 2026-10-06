"""Application service for the current-recommendation endpoint.
Respects Phase 14 safety suppression -- never bypasses it."""

from __future__ import annotations

from app.api.errors import NotFoundError
from app.api.formatting import format_time
from app.api.repositories.circadian_repository import CircadianRepository
from app.api.repositories.intervention_repository import InterventionRepository
from app.api.repositories.safety_repository import SafetyRepository
from app.api.schemas.recommendation import PrimaryRecommendation, RecommendationResponse
from app.safety.enums import HIGH
from app.safety.messages import HIGH_SEVERITY_SUPPRESSION_MESSAGE, NON_DIAGNOSTIC_STATEMENT


class RecommendationService:
    def __init__(
        self, circadian_repository: CircadianRepository, intervention_repository: InterventionRepository, safety_repository: SafetyRepository
    ):
        self.circadian_repository = circadian_repository
        self.intervention_repository = intervention_repository
        self.safety_repository = safety_repository

    def get_current(self, participant_id: int) -> RecommendationResponse:
        label = self.circadian_repository.get_latest(participant_id)
        if label is None:
            raise NotFoundError("No daily result exists yet for this participant", detail=f"participant_id={participant_id}")

        active_flags = self.safety_repository.get_active_flags(participant_id)
        highest_severity = label.safety_severity or (HIGH if any(f.severity == HIGH for f in active_flags) else None)
        suppressed = label.recommendation_suppressed if label.recommendation_suppressed is not None else (highest_severity == HIGH)

        if suppressed:
            return RecommendationResponse(
                participant_id=participant_id, available=False, suppressed=True,
                safety_message=HIGH_SEVERITY_SUPPRESSION_MESSAGE, non_diagnostic_statement=NON_DIAGNOSTIC_STATEMENT,
            )

        logs = self.intervention_repository.get_history(participant_id, label.target_date, label.target_date, None, 1)
        if not logs:
            return RecommendationResponse(participant_id=participant_id, available=False, suppressed=False)

        log = logs[0]
        recommendation_row = self.intervention_repository.get_recommendation(log.recommendation_id)

        primary = PrimaryRecommendation(
            intervention_type=recommendation_row.intervention_type if recommendation_row else "unknown",
            text=log.recommendation_text or "",
            target_display=format_time(log.target_value_time) if log.target_value_time is not None else (
                str(log.target_value_numeric) if log.target_value_numeric is not None else None
            ),
            expected_improvement_minutes=log.expected_improvement_minutes,
            expected_improvement_source=log.personalization_phase,
        )

        return RecommendationResponse(
            participant_id=participant_id, available=True, suppressed=False, primary=primary,
            supporting=[], personalization_phase=log.personalization_phase,
        )
