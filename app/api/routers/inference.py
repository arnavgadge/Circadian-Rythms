from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_inference_service
from app.api.schemas.inference import InferenceRequest, InferenceResponse
from app.api.services.inference_service import InferenceService

router = APIRouter(prefix="/participants", tags=["inference"])


@router.post(
    "/{participant_id}/inference",
    response_model=InferenceResponse,
    summary="Run daily inference",
    description=(
        "Invokes the existing Phase 11 daily inference pipeline (feature engineering -> XGBoost + state "
        "engine -> fusion -> alignment -> contributors -> recommendation) followed by the Phase 14 safety "
        "evaluation. Idempotent: repeating the same participant/date without force_rerun returns the "
        "existing persisted result rather than duplicating it."
    ),
)
def run_inference(participant_id: int, request: InferenceRequest, service: InferenceService = Depends(get_inference_service)) -> InferenceResponse:
    return service.run(participant_id, request.target_date, request.force_rerun)
