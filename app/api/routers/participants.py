from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_participant_service, get_status_service
from app.api.schemas.participant import ParticipantResponse
from app.api.schemas.status import StatusResponse
from app.api.services.participant_service import ParticipantService
from app.api.services.status_service import StatusService

router = APIRouter(prefix="/participants", tags=["participants"])


@router.get(
    "/{participant_id}",
    response_model=ParticipantResponse,
    summary="Get participant profile",
    description="Safe participant-level information: chronotype, estimated biological clock, current alignment. Never a clinical measurement.",
)
def get_participant(participant_id: int, service: ParticipantService = Depends(get_participant_service)) -> ParticipantResponse:
    return service.get_participant(participant_id)


@router.get(
    "/{participant_id}/status",
    response_model=StatusResponse,
    summary="Get current circadian status",
    description=(
        "Reads the latest persisted daily-inference + safety-layer result. Does NOT trigger a new inference "
        "run -- use POST /inference for that. Estimated from behavioral patterns, not a clinical measurement."
    ),
)
def get_status(
    participant_id: int,
    target_date: Optional[date_type] = Query(default=None, description="Defaults to the most recent available result."),
    service: StatusService = Depends(get_status_service),
) -> StatusResponse:
    return service.build_status(participant_id, target_date)
