from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_participant_service
from app.api.schemas.onboarding import OnboardingRequest, OnboardingResponse
from app.api.services.participant_service import ParticipantService

router = APIRouter(tags=["onboarding"])


@router.post(
    "/participants",
    response_model=OnboardingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Onboard a new participant",
    description=(
        "Creates a participant record and stores any supplied questionnaire baseline (MEQ, MSFsc). "
        "Does not compute an estimated biological clock from questionnaire data alone -- CircadianIQ "
        "estimates circadian phase from behavioral patterns, not a one-time questionnaire."
    ),
)
def onboard_participant(request: OnboardingRequest, service: ParticipantService = Depends(get_participant_service)) -> OnboardingResponse:
    return service.onboard(request)
