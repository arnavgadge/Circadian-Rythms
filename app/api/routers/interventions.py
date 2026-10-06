from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_intervention_service
from app.api.schemas.interventions import InterventionHistoryResponse, OutcomeSubmissionRequest, OutcomeSubmissionResponse
from app.api.services.intervention_service import InterventionService

router = APIRouter(prefix="/participants", tags=["interventions"])


@router.get(
    "/{participant_id}/interventions",
    response_model=InterventionHistoryResponse,
    summary="Get intervention history",
    description="Recommended interventions, targets, actual values, compliance, and (where available) effect estimates.",
)
def get_intervention_history(
    participant_id: int,
    start_date: Optional[date_type] = Query(default=None),
    end_date: Optional[date_type] = Query(default=None),
    intervention_type: Optional[str] = Query(default=None),
    limit: int = Query(default=30, ge=1, le=365),
    service: InterventionService = Depends(get_intervention_service),
) -> InterventionHistoryResponse:
    return service.get_history(participant_id, start_date, end_date, intervention_type, limit)


@router.post(
    "/{participant_id}/interventions/{intervention_log_id}/outcome",
    response_model=OutcomeSubmissionResponse,
    summary="Record an observed intervention outcome",
    description=(
        "Records the participant's actual behavior for a previously-recommended intervention day. "
        "Compliance is computed by the existing Phase 12 compliance evaluator -- never recalculated here."
    ),
)
def submit_intervention_outcome(
    participant_id: int,
    intervention_log_id: int,
    request: OutcomeSubmissionRequest,
    service: InterventionService = Depends(get_intervention_service),
) -> OutcomeSubmissionResponse:
    return service.submit_outcome(participant_id, intervention_log_id, request)
