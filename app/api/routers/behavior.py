from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_behavior_service
from app.api.schemas.behavior import BehaviorHistoryResponse
from app.api.schemas.daily_entry import DailyEntryRequest, DailyEntryResponse
from app.api.services.behavior_service import BehaviorService

router = APIRouter(prefix="/participants", tags=["behavior"])


@router.get(
    "/{participant_id}/behavior",
    response_model=BehaviorHistoryResponse,
    summary="Get recent behavioral observations",
    description="Recent logged sleep/light/screen/meal/exercise observations. Supports optional date filtering.",
)
def get_behavior_history(
    participant_id: int,
    start_date: Optional[date_type] = Query(default=None),
    end_date: Optional[date_type] = Query(default=None),
    limit: int = Query(default=30, ge=1, le=365),
    service: BehaviorService = Depends(get_behavior_service),
) -> BehaviorHistoryResponse:
    return service.get_history(participant_id, start_date, end_date, limit)


@router.post(
    "/{participant_id}/behavior",
    response_model=DailyEntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a day's manually-logged behavioral baseline",
    description=(
        "Creates or updates the one daily_observations row for this participant/date. Pure data capture -- "
        "computes nothing (sleep duration, tiers, etc. remain the feature-engineering layer's job)."
    ),
)
def record_daily_entry(
    participant_id: int, request: DailyEntryRequest, service: BehaviorService = Depends(get_behavior_service)
) -> DailyEntryResponse:
    return service.record_entry(participant_id, request)
