"""The contextual-bandit state: a small, interpretable feature set --
deliberately not dozens of arbitrary features (see
``docs/personalization_engine.md`` "Bandit reward"/"contextual bandit").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class BanditContext:
    current_dlmo_hour: Optional[float]
    alignment_score: Optional[float]
    top_contributor_signal: Optional[str]
    day_of_week: int  # 0=Monday .. 6=Sunday
    upcoming_free_days: int  # count of free days in the next 7 days
    recent_compliance_rate: Optional[float]
    weeks_active: float
    current_severity: str  # "good" | "mild" | "moderate" | "severe" (app.recommendations.severity)


def build_context(
    current_dlmo_hour: Optional[float],
    alignment_score: Optional[float],
    top_contributor_signal: Optional[str],
    day_of_week: int,
    upcoming_free_days: int,
    recent_compliance_rate: Optional[float],
    weeks_active: float,
    current_severity: str,
) -> BanditContext:
    return BanditContext(
        current_dlmo_hour=current_dlmo_hour,
        alignment_score=alignment_score,
        top_contributor_signal=top_contributor_signal,
        day_of_week=day_of_week,
        upcoming_free_days=upcoming_free_days,
        recent_compliance_rate=recent_compliance_rate,
        weeks_active=weeks_active,
        current_severity=current_severity,
    )
