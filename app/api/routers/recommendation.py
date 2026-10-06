from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_recommendation_service
from app.api.schemas.recommendation import RecommendationResponse
from app.api.services.recommendation_service import RecommendationService

router = APIRouter(prefix="/participants", tags=["recommendation"])


@router.get(
    "/{participant_id}/recommendation/current",
    response_model=RecommendationResponse,
    summary="Get current recommendation",
    description=(
        "The current primary behavioral recommendation, if any. Respects Phase 14 safety suppression: "
        "if a HIGH-severity safety flag is active, the recommendation is unavailable and a safe message "
        "is returned instead. Never bypasses the safety layer."
    ),
)
def get_current_recommendation(participant_id: int, service: RecommendationService = Depends(get_recommendation_service)) -> RecommendationResponse:
    return service.get_current(participant_id)
