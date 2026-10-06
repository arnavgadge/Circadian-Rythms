"""Application service for behavioral-history reads and daily manual
entry. ``record_entry`` is pure data capture -- it parses the request's
HH:MM strings into ``datetime.time`` values and persists them; it does
not compute sleep duration, tiers, or anything Phase 4's feature
engine is responsible for.
"""

from __future__ import annotations

from datetime import date as date_type, time as time_type
from typing import Optional

from sqlalchemy.orm import Session

from app.api.errors import NotFoundError
from app.api.formatting import format_time
from app.api.repositories.behavior_repository import BehaviorRepository
from app.api.repositories.participant_repository import ParticipantRepository
from app.api.schemas.behavior import BehaviorEntry, BehaviorHistoryResponse
from app.api.schemas.daily_entry import DailyEntryRequest, DailyEntryResponse


def _parse_time(value: Optional[str]) -> Optional[time_type]:
    if value is None:
        return None
    hour, minute = (int(p) for p in value.split(":"))
    return time_type(hour=hour, minute=minute)


class BehaviorService:
    def __init__(self, repository: BehaviorRepository, session: Session):
        self.repository = repository
        self.session = session
        self.participant_repository = ParticipantRepository(session)

    def get_history(
        self, participant_id: int, start_date: Optional[date_type], end_date: Optional[date_type], limit: int
    ) -> BehaviorHistoryResponse:
        rows = self.repository.get_history(participant_id, start_date, end_date, limit)
        entries = [
            BehaviorEntry(
                date=row.observation_date,
                sleep_onset=format_time(row.sleep_onset_time),
                morning_light_duration_minutes=row.morning_light_duration_minutes,
                evening_screen_duration_minutes=row.evening_screen_duration_minutes,
                last_meal_time=format_time(row.last_meal_time),
                exercise_time=format_time(row.exercise_time),
                is_free_day=row.is_free_day,
            )
            for row in rows
        ]
        return BehaviorHistoryResponse(participant_id=participant_id, entries=entries, count=len(entries))

    def record_entry(self, participant_id: int, request: DailyEntryRequest) -> DailyEntryResponse:
        if self.participant_repository.get(participant_id) is None:
            raise NotFoundError("Participant not found", detail=f"participant_id={participant_id}")

        self.repository.upsert(
            participant_id,
            request.observation_date,
            sleep_onset_time=_parse_time(request.sleep_onset_time),
            sleep_offset_time=_parse_time(request.sleep_offset_time),
            morning_light_start_time=_parse_time(request.morning_light_start_time),
            morning_light_duration_minutes=request.morning_light_duration_minutes,
            evening_screen_end_time=_parse_time(request.evening_screen_end_time),
            evening_screen_duration_minutes=request.evening_screen_duration_minutes,
            last_meal_time=_parse_time(request.last_meal_time),
            exercise_time=_parse_time(request.exercise_time),
            last_caffeine_time=_parse_time(request.last_caffeine_time),
            caffeine_amount_mg=request.caffeine_amount_mg,
            is_free_day=request.is_free_day,
        )
        self.session.commit()
        return DailyEntryResponse(participant_id=participant_id, observation_date=request.observation_date, saved=True)
