from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_contributor_service
from app.api.schemas.contributors import ContributorsResponse
from app.api.services.contributor_service import ContributorService

router = APIRouter(prefix="/participants", tags=["contributors"])


@router.get(
    "/{participant_id}/contributors/current",
    response_model=ContributorsResponse,
    summary="Get current top contributors",
    description="The ranked behavioral signals most associated with current misalignment -- modeled influence, never a proven cause.",
)
def get_current_contributors(participant_id: int, service: ContributorService = Depends(get_contributor_service)) -> ContributorsResponse:
    return service.get_current(participant_id)
