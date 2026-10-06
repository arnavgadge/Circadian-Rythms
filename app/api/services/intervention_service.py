"""Application service for intervention history + outcome submission.
Outcome submission reuses Phase 12's own compliance evaluator
(``app.effectiveness.compliance.evaluate_compliance``) -- the route
never computes a compliance degree itself.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.api.errors import NotFoundError, ValidationFailedError
from app.api.formatting import format_time
from app.api.repositories.intervention_repository import InterventionRepository
from app.api.schemas.interventions import (
    InterventionHistoryEntry,
    InterventionHistoryResponse,
    OutcomeSubmissionRequest,
    OutcomeSubmissionResponse,
)
from app.effectiveness.compliance import evaluate_compliance, resolve_dispatch_key
from app.effectiveness.config import DEFAULT_EFFECTIVENESS_CONFIG
from app.recommendations.catalogue import CLOCK_HOUR, intervention_from_recommendation
from app.synthetic.time_utils import clock_time_to_hour, hour_to_clock_time


class InterventionService:
    def __init__(self, repository: InterventionRepository, session: Session):
        self.repository = repository
        self.session = session

    def get_history(
        self, participant_id: int, start_date, end_date, intervention_type: Optional[str], limit: int
    ) -> InterventionHistoryResponse:
        rows = self.repository.get_history(participant_id, start_date, end_date, intervention_type, limit)
        entries = []
        for row in rows:
            recommendation = self.repository.get_recommendation(row.recommendation_id)
            estimate = self.repository.get_latest_effect_estimate(participant_id, row.recommendation_id)
            entries.append(
                InterventionHistoryEntry(
                    intervention_log_id=row.id,
                    intervention_code=recommendation.intervention_code if recommendation else "unknown",
                    intervention_type=recommendation.intervention_type if recommendation else "unknown",
                    log_date=row.log_date,
                    target_display=format_time(row.target_value_time) if row.target_value_time is not None else (
                        str(row.target_value_numeric) if row.target_value_numeric is not None else None
                    ),
                    actual_display=format_time(row.actual_value_time) if row.actual_value_time is not None else (
                        str(row.actual_value_numeric) if row.actual_value_numeric is not None else None
                    ),
                    compliance_degree=row.compliance_degree,
                    compliance_binary=row.compliance_binary,
                    observation_status="observed" if row.compliance_degree is not None else "missing",
                    measurement_phase=estimate.measurement_phase if estimate else None,
                    effect_estimate=estimate.effect_estimate if estimate else None,
                )
            )
        return InterventionHistoryResponse(participant_id=participant_id, entries=entries, count=len(entries))

    def submit_outcome(self, participant_id: int, intervention_log_id: int, request: OutcomeSubmissionRequest) -> OutcomeSubmissionResponse:
        log = self.repository.get_log(intervention_log_id)
        if log is None or log.participant_id != participant_id:
            raise NotFoundError("Intervention log entry not found", detail=f"intervention_log_id={intervention_log_id}")
        if log.log_date != request.observation_date:
            raise ValidationFailedError(
                "observation_date does not match this intervention log entry's own date",
                detail=f"expected {log.log_date}, got {request.observation_date}",
            )

        if not request.observed or (request.actual_value_time is None and request.actual_value_numeric is None):
            # Explicit missing observation -- never treated as non-compliance.
            log.compliance_degree = None
            log.compliance_binary = None
            self.session.commit()
            return OutcomeSubmissionResponse(
                intervention_log_id=log.id, observation_date=log.log_date, compliance_degree=None, compliance_binary=None, applied=False
            )

        recommendation = self.repository.get_recommendation(log.recommendation_id)
        if recommendation is None:
            raise NotFoundError("Underlying recommendation catalogue entry not found", detail=f"recommendation_id={log.recommendation_id}")

        candidate = intervention_from_recommendation(recommendation)
        signal = resolve_dispatch_key(candidate.contributor_signals, candidate.intervention_type)

        target_value = clock_time_to_hour(log.target_value_time) if log.target_value_time is not None else log.target_value_numeric

        if candidate.value_kind == CLOCK_HOUR:
            if request.actual_value_time is None:
                raise ValidationFailedError("This intervention expects a clock-time actual_value_time")
            hour, minute = (int(p) for p in request.actual_value_time.split(":"))
            actual_value = hour + minute / 60.0
        else:
            if request.actual_value_numeric is None:
                raise ValidationFailedError("This intervention expects a numeric actual_value_numeric")
            actual_value = request.actual_value_numeric

        result = evaluate_compliance(signal, target_value, actual_value, DEFAULT_EFFECTIVENESS_CONFIG)

        if not result.available:
            self.session.commit()
            return OutcomeSubmissionResponse(
                intervention_log_id=log.id, observation_date=log.log_date, compliance_degree=None, compliance_binary=None, applied=False
            )

        log.compliance_degree = result.compliance_degree
        log.compliance_binary = result.compliance_binary
        if candidate.value_kind == CLOCK_HOUR:
            log.actual_value_time = hour_to_clock_time(actual_value)
        else:
            log.actual_value_numeric = actual_value
        self.session.commit()

        return OutcomeSubmissionResponse(
            intervention_log_id=log.id, observation_date=log.log_date,
            compliance_degree=result.compliance_degree, compliance_binary=result.compliance_binary, applied=True,
        )
