"""Small, shared display-formatting helpers for API responses --
24-hour ``HH:MM`` strings, matching the API response examples in the
Phase 15 brief. Never a source of computation: these only format
values already computed elsewhere.
"""

from __future__ import annotations

from datetime import time as time_type
from typing import Optional


def format_time(value: Optional[time_type]) -> Optional[str]:
    return value.strftime("%H:%M") if value is not None else None


def format_hour(hour: Optional[float]) -> Optional[str]:
    if hour is None:
        return None
    from app.synthetic.time_utils import hour_to_clock_time

    return format_time(hour_to_clock_time(hour))
