"""Read-side adapter between the Phase 2 database and the contributor
ranking engine.

Builds a :class:`~app.contributors.inputs.ContributorInputs` from a
participant's ``daily_observations`` rows, the same
:class:`~app.state.circadian_state.ParticipantPhaseTraits` Phase 6
already uses, and an already-computed Phase 8
:class:`~app.alignment.engine.AlignmentResult` -- mirroring the
read-only adapter pattern established in ``app.state.db_adapter`` and
``app.alignment.db_adapter``. No new table is introduced; this module
only reads existing rows. Writing a persisted contributor-ranking
result is left to whatever later phase owns that write path.
"""

from __future__ import annotations

from datetime import date
from typing import Optional, Sequence

from app.alignment.engine import AlignmentResult
from app.contributors.inputs import ContributorInputs
from app.database.models import DailyObservation
from app.state.circadian_state import ParticipantPhaseTraits
from app.synthetic.time_utils import clock_time_to_hour


def _hour_or_none(value) -> Optional[float]:
    return clock_time_to_hour(value) if value is not None else None


def build_contributor_inputs(
    traits: ParticipantPhaseTraits,
    alignment_result: AlignmentResult,
    window_observations: Sequence[DailyObservation],
    latest_observation: Optional[DailyObservation] = None,
) -> ContributorInputs:
    """Build :class:`ContributorInputs` from raw ``daily_observations`` rows.

    ``window_observations`` must be the six most recent complete days,
    ordered oldest to newest (Phase 4's window convention) -- the
    habit-level history the ranking is based on. ``latest_observation``
    is today's/most-recently-completed day, used only for the separate
    anomaly comparison; if not given, it defaults to the last entry of
    ``window_observations`` (matching the alignment adapter's
    convention), so the two only diverge when a caller explicitly has a
    newer day than what is in the six-day window.
    """

    if latest_observation is None and window_observations:
        latest_observation = window_observations[-1]

    window_dates = [o.observation_date for o in window_observations] or None

    return ContributorInputs(
        traits=traits,
        alignment_result=alignment_result,
        window_morning_light_duration_minutes=[o.morning_light_duration_minutes for o in window_observations],
        window_evening_screen_duration_hours=[
            (o.evening_screen_duration_minutes / 60.0) if o.evening_screen_duration_minutes is not None else None
            for o in window_observations
        ],
        window_last_meal_hours=[_hour_or_none(o.last_meal_time) for o in window_observations],
        window_exercise_hours=[_hour_or_none(o.exercise_time) for o in window_observations],
        window_social_jetlag_minutes=[o.social_jetlag_minutes for o in window_observations],
        latest_morning_light_duration_minutes=(
            latest_observation.morning_light_duration_minutes if latest_observation is not None else None
        ),
        latest_evening_screen_duration_hours=(
            (latest_observation.evening_screen_duration_minutes / 60.0)
            if latest_observation is not None and latest_observation.evening_screen_duration_minutes is not None
            else None
        ),
        latest_last_meal_hour=(
            _hour_or_none(latest_observation.last_meal_time) if latest_observation is not None else None
        ),
        latest_exercise_hour=(
            _hour_or_none(latest_observation.exercise_time) if latest_observation is not None else None
        ),
        latest_social_jetlag_minutes=(
            latest_observation.social_jetlag_minutes if latest_observation is not None else None
        ),
        window_dates=window_dates,
    )
