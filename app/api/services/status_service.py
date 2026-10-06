"""Builds the composite ``StatusResponse`` from already-persisted state
only -- **never** runs inference. Reused by both ``GET /status`` and
the tail of ``POST /inference`` (so both paths render identically).
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from app.api.errors import NotFoundError
from app.api.formatting import format_hour, format_time
from app.api.repositories.circadian_repository import CircadianRepository
from app.api.repositories.intervention_repository import InterventionRepository
from app.api.repositories.participant_repository import ParticipantRepository
from app.api.repositories.safety_repository import SafetyRepository
from app.api.schemas.status import (
    AlignmentComponents,
    AlignmentSummary,
    ConfidenceSummary,
    ContributorSummary,
    RecommendationSummary,
    SafetySummary,
    StatusResponse,
)
from app.safety.enums import HIGH
from app.safety.messages import HIGH_SEVERITY_SUPPRESSION_MESSAGE, INSUFFICIENT_DATA_GUIDANCE, QUALIFIER_LOW, QUALIFIER_MODERATE


class StatusService:
    def __init__(
        self,
        participant_repository: ParticipantRepository,
        circadian_repository: CircadianRepository,
        intervention_repository: InterventionRepository,
        safety_repository: SafetyRepository,
    ):
        self.participant_repository = participant_repository
        self.circadian_repository = circadian_repository
        self.intervention_repository = intervention_repository
        self.safety_repository = safety_repository

    def build_status(self, participant_id: int, target_date: Optional[date_type] = None) -> StatusResponse:
        if self.participant_repository.get(participant_id) is None:
            raise NotFoundError("Participant not found", detail=f"participant_id={participant_id}")

        label = (
            self.circadian_repository.get_for_date(participant_id, target_date)
            if target_date is not None
            else self.circadian_repository.get_latest(participant_id)
        )

        if label is None:
            return StatusResponse(
                participant_id=participant_id, prediction_available=False,
                alignment=AlignmentSummary(), confidence=ConfidenceSummary(approximate=False),
                recommendation=RecommendationSummary(available=False),
                safety=SafetySummary(active=False),
                qualifier_message="No daily result exists yet for this participant/date.",
            )

        profile = self.participant_repository.get_profile(participant_id)

        prediction_available = label.fused_dlmo_time is not None and label.confidence_label != "no_prediction"
        approximate = label.confidence_label == "low"
        if label.confidence_label == "low":
            qualifier = QUALIFIER_LOW
        elif label.confidence_label == "moderate":
            qualifier = QUALIFIER_MODERATE
        elif not prediction_available:
            qualifier = INSUFFICIENT_DATA_GUIDANCE
        else:
            qualifier = None

        alignment_row = label.alignment_result
        alignment = AlignmentSummary(
            score=alignment_row.final_alignment_score if alignment_row else None,
            phase_score=alignment_row.phase_alignment_score if alignment_row else None,
            behavioral_score=alignment_row.behavioral_alignment_score if alignment_row else None,
            components=AlignmentComponents(
                sleep_consistency=alignment_row.sleep_consistency_score,
                morning_light=alignment_row.morning_light_score,
                evening_screen=alignment_row.evening_screen_score,
                meal_timing=alignment_row.meal_timing_score,
                social_jetlag=alignment_row.social_jetlag_score,
            ) if alignment_row else None,
            ideal_sleep_onset=format_time(alignment_row.ideal_sleep_onset_time) if alignment_row else None,
            actual_sleep_onset=format_time(alignment_row.actual_sleep_onset_time) if alignment_row else None,
        )

        contributors = []
        if alignment_row is not None:
            for row in self.circadian_repository.get_contributors(label.id):
                contributors.append(
                    ContributorSummary(
                        rank=row.rank, signal=row.contributor_signal, effect_minutes=row.effect_estimate,
                        alignment_deficit=row.alignment_deficit, contributor_score=row.contributor_score,
                        direction=row.direction, today_anomaly=row.today_anomaly,
                    )
                )

        active_flag_rows = self.safety_repository.get_active_flags(participant_id)
        highest_severity = label.safety_severity or (HIGH if any(f.severity == HIGH for f in active_flag_rows) else ("MODERATE" if active_flag_rows else None))
        recommendation_suppressed = label.recommendation_suppressed if label.recommendation_suppressed is not None else (highest_severity == HIGH)

        safety = SafetySummary(
            active=bool(active_flag_rows), highest_severity=highest_severity,
            recommendation_suppressed=recommendation_suppressed,
            flag_types=[f.flag_type for f in active_flag_rows],
        )

        recommendation = self._build_recommendation_summary(participant_id, label.target_date, recommendation_suppressed)

        return StatusResponse(
            participant_id=participant_id,
            prediction_available=prediction_available,
            biological_clock=format_time(label.fused_dlmo_time),
            chronotype=profile.chronotype_category if profile else None,
            approximate=approximate,
            alignment=alignment,
            confidence=ConfidenceSummary(score=label.confidence_score, label=label.confidence_label, approximate=approximate),
            contributors=contributors,
            recommendation=recommendation,
            safety=safety,
            target_date=str(label.target_date),
            qualifier_message=qualifier,
        )

    def _build_recommendation_summary(self, participant_id: int, target_date: date_type, suppressed: bool) -> RecommendationSummary:
        if suppressed:
            return RecommendationSummary(available=False, suppressed=True)

        logs = self.intervention_repository.get_history(participant_id, target_date, target_date, None, 1)
        if not logs:
            return RecommendationSummary(available=False, suppressed=False)

        log = logs[0]
        recommendation_row = self.intervention_repository.get_recommendation(log.recommendation_id)
        return RecommendationSummary(
            available=True, suppressed=False,
            intervention_type=recommendation_row.intervention_type if recommendation_row else None,
            text=log.recommendation_text,
            target_display=format_time(log.target_value_time) if log.target_value_time is not None else (
                str(log.target_value_numeric) if log.target_value_numeric is not None else None
            ),
            expected_improvement_minutes=log.expected_improvement_minutes,
            expected_improvement_source=log.personalization_phase,
        )
