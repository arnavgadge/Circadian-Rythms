from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_safety_service
from app.api.schemas.safety import SafetyStatusResponse
from app.api.services.safety_service import SafetyService

router = APIRouter(prefix="/participants", tags=["safety"])


@router.get(
    "/{participant_id}/safety",
    response_model=SafetyStatusResponse,
    summary="Get safety status",
    description="Active safety flags, highest severity, prediction availability, and recommendation-suppression state. Screening only, never a diagnosis.",
)
def get_safety_status(participant_id: int, service: SafetyService = Depends(get_safety_service)) -> SafetyStatusResponse:
    return service.get_status(participant_id)
