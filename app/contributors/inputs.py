"""Input types for the contributor ranking engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_cls
from typing import Optional

from app.alignment.engine import AlignmentResult
from app.state.circadian_state import ParticipantPhaseTraits


@dataclass(frozen=True)
class ContributorInputs:
    """Everything :func:`app.contributors.engine.rank_contributors` needs.

    ``window_*`` sequences are the six most recent days, oldest to
    newest (Phase 4's window convention) -- the "habit-level" history
    the ranking is based on. ``latest_*`` values are today's/most
    recently completed observations, used **only** for the separate
    today's-anomaly comparison (see ``docs/contributor_ranking.md``
    "Today's anomaly detection") -- they never feed into the six-day
    ranking itself.

    ``alignment_result`` is Phase 8's output for this same day, reused
    for its behavioral-component scores (never recomputed here).
    ``traits`` supplies the participant sensitivities and baseline
    sleep-onset trait the shared Phase 6 effect model needs.
    """

    traits: ParticipantPhaseTraits
    alignment_result: AlignmentResult

    window_morning_light_duration_minutes: list = field(default_factory=list)
    window_evening_screen_duration_hours: list = field(default_factory=list)
    window_last_meal_hours: list = field(default_factory=list)
    window_exercise_hours: list = field(default_factory=list)
    window_social_jetlag_minutes: list = field(default_factory=list)

    # Optional "today" observations for anomaly detection only.
    latest_morning_light_duration_minutes: Optional[float] = None
    latest_evening_screen_duration_hours: Optional[float] = None
    latest_last_meal_hour: Optional[float] = None
    latest_exercise_hour: Optional[float] = None
    latest_social_jetlag_minutes: Optional[float] = None

    # Optional, purely for traceability in the returned result.
    window_dates: Optional[list] = None
