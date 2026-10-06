from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_health_service
from app.api.schemas.health import HealthResponse
from app.api.services.health_service import HealthService

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Application health check",
    description="Reports application/database/model-artifact/configuration readiness. Never exposes internal file paths.",
)
def get_health(service: HealthService = Depends(get_health_service)) -> HealthResponse:
    return service.check()
