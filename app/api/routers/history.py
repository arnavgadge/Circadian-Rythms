from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_history_service
from app.api.schemas.history import CircadianHistoryResponse
from app.api.services.history_service import HistoryService

router = APIRouter(prefix="/participants", tags=["history"])


@router.get(
    "/{participant_id}/circadian/history",
    response_model=CircadianHistoryResponse,
    summary="Get historical circadian trajectory",
    description="Historical estimated biological clock, confidence, alignment, and disagreement regime -- read-only.",
)
def get_circadian_history(
    participant_id: int,
    start_date: Optional[date_type] = Query(default=None),
    end_date: Optional[date_type] = Query(default=None),
    limit: int = Query(default=30, ge=1, le=365),
    service: HistoryService = Depends(get_history_service),
) -> CircadianHistoryResponse:
    return service.get_history(participant_id, start_date, end_date, limit)
