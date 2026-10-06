from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from pydantic import BaseModel


class BehaviorEntry(BaseModel):
    date: date_type
    sleep_onset: Optional[str] = None
    morning_light_duration_minutes: Optional[float] = None
    evening_screen_duration_minutes: Optional[float] = None
    last_meal_time: Optional[str] = None
    exercise_time: Optional[str] = None
    is_free_day: Optional[bool] = None


class BehaviorHistoryResponse(BaseModel):
    participant_id: int
    entries: list
    count: int
