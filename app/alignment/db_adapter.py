"""Read-side adapter between the Phase 2 database and the alignment engine.

Builds an :class:`~app.alignment.inputs.AlignmentInputs` from a
participant's ``daily_observations`` rows and a fused DLMO value
(Phase 7's output, e.g. ``circadian_labels.fused_dlmo_time`` for the
target date) -- read-only, mirroring the pattern established in
``app.state.db_adapter``. Writing the resulting alignment score back
into ``circadian_labels`` is left to whatever later phase owns that
write path; this module only reads.
"""

from __future__ import annotations

from datetime import date
from typing import Optional, Sequence

from app.alignment.inputs import AlignmentInputs
from app.database.models import DailyObservation
from app.synthetic.time_utils import clock_time_to_hour


def _hour_or_none(value) -> Optional[float]:
    return clock_time_to_hour(value) if value is not None else None


def build_alignment_inputs(
    fused_dlmo_hour: float,
    window_observations: Sequence[DailyObservation],
    most_recent_observation: Optional[DailyObservation] = None,
    chronotype: Optional[str] = None,
) -> AlignmentInputs:
    """Build :class:`AlignmentInputs` from raw ``daily_observations`` rows.

    ``window_observations`` must be the six most recent complete days,
    ordered oldest to newest (matching Phase 4's window convention);
    missing days should be represented by omission (the caller is
    responsible for knowing which dates are missing -- this function
    only reads whatever rows it is given). ``most_recent_observation``
    is the single most-recently-completed day, used only for phase
    alignment; if not given, it defaults to the last entry of
    ``window_observations``.
    """

    if most_recent_observation is None and window_observations:
        most_recent_observation = window_observations[-1]

    most_recent_sleep_onset_hour = (
        _hour_or_none(most_recent_observation.sleep_onset_time) if most_recent_observation is not None else None
    )

    return AlignmentInputs(
        fused_dlmo_hour=fused_dlmo_hour,
        most_recent_sleep_onset_hour=most_recent_sleep_onset_hour,
        window_sleep_onset_hours=[_hour_or_none(o.sleep_onset_time) for o in window_observations],
        window_morning_light_duration_minutes=[o.morning_light_duration_minutes for o in window_observations],
        window_evening_screen_duration_hours=[
            (o.evening_screen_duration_minutes / 60.0) if o.evening_screen_duration_minutes is not None else None
            for o in window_observations
        ],
        window_last_meal_hours=[_hour_or_none(o.last_meal_time) for o in window_observations],
        window_social_jetlag_minutes=[o.social_jetlag_minutes for o in window_observations],
        chronotype=chronotype,
    )
