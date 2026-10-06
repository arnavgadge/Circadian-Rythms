from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from pydantic import BaseModel, Field


class HistoryQuery(BaseModel):
    start_date: Optional[date_type] = None
    end_date: Optional[date_type] = None
    limit: int = Field(default=30, ge=1, le=365)


class CircadianHistoryEntry(BaseModel):
    date: date_type
    biological_clock: Optional[str] = None
    confidence_score: Optional[float] = None
    confidence_label: Optional[str] = None
    alignment_score: Optional[float] = None
    disagreement_regime: Optional[str] = None
    prediction_status: str


class CircadianHistoryResponse(BaseModel):
    participant_id: int
    entries: list
    count: int
