"""Six-day window identification.

A window covers exactly six *consecutive* calendar days
(``window_start`` .. ``window_end``, oldest to newest) and predicts
``target_date == window_end + 1 day``. Windows are computed directly
from whatever ``daily_observations`` dates actually exist for a
participant in the database -- never assumed to be "days 1-30" -- so
this is robust to gaps and works identically regardless of which phase
produced the underlying data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Sequence


@dataclass(frozen=True)
class Window:
    """A single six-day feature window and its prediction target date.

    ``day_dates`` is always exactly six dates, strictly increasing by
    one calendar day each step, oldest first (``day_dates[0]`` = day_1,
    ``day_dates[5]`` = day_6). ``target_date`` is always exactly one day
    after ``day_dates[-1]``.
    """

    participant_id: int
    window_start: date
    window_end: date
    target_date: date
    day_dates: tuple

    def __post_init__(self) -> None:
        if len(self.day_dates) != 6:
            raise ValueError(f"Window requires exactly 6 day_dates, got {len(self.day_dates)}")
        for i in range(1, 6):
            if (self.day_dates[i] - self.day_dates[i - 1]) != timedelta(days=1):
                raise ValueError(f"Window day_dates must be consecutive: {self.day_dates}")
        if self.day_dates[0] != self.window_start or self.day_dates[-1] != self.window_end:
            raise ValueError("window_start/window_end must match day_dates bounds")
        if self.target_date != self.window_end + timedelta(days=1):
            raise ValueError("target_date must be exactly one day after window_end")


def compute_valid_windows(
    participant_id: int, available_dates: Sequence[date], window_size_days: int = 6
) -> list:
    """Compute every valid window for a participant from their available dates.

    A window is valid at position ``i`` when ``available_dates[i ..
    i+window_size_days]`` (inclusive of the target date) are all present
    and form ``window_size_days + 1`` strictly consecutive calendar
    days. ``available_dates`` need not be pre-sorted or de-duplicated.
    """

    dates = sorted(set(available_dates))
    windows: list = []

    for i in range(len(dates) - window_size_days):
        span = dates[i : i + window_size_days + 1]
        if len(span) != window_size_days + 1:
            continue
        if all((span[j + 1] - span[j]) == timedelta(days=1) for j in range(len(span) - 1)):
            windows.append(
                Window(
                    participant_id=participant_id,
                    window_start=span[0],
                    window_end=span[window_size_days - 1],
                    target_date=span[window_size_days],
                    day_dates=tuple(span[:window_size_days]),
                )
            )

    return windows
