"""Application service for the historical circadian trajectory endpoint."""

from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from app.api.formatting import format_time
from app.api.repositories.circadian_repository import CircadianRepository
from app.api.schemas.history import CircadianHistoryEntry, CircadianHistoryResponse


class HistoryService:
    def __init__(self, repository: CircadianRepository):
        self.repository = repository

    def get_history(
        self, participant_id: int, start_date: Optional[date_type], end_date: Optional[date_type], limit: int
    ) -> CircadianHistoryResponse:
        rows = self.repository.get_history(participant_id, start_date, end_date, limit)
        entries = [
            CircadianHistoryEntry(
                date=row.target_date,
                biological_clock=format_time(row.fused_dlmo_time),
                confidence_score=row.confidence_score,
                confidence_label=row.confidence_label,
                alignment_score=row.alignment_result.final_alignment_score if row.alignment_result else None,
                disagreement_regime=row.disagreement_regime,
                prediction_status=row.prediction_status,
            )
            for row in rows
        ]
        return CircadianHistoryResponse(participant_id=participant_id, entries=entries, count=len(entries))
