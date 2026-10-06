"""Phase alignment: actual sleep onset vs. the ideal sleep onset implied
by the fused DLMO.

Uses the single most-recently-completed sleep period (not a six-day
average -- see ``docs/alignment_engine.md`` "Time horizons"). All
comparisons use the shortest **signed circular** difference; never a
naive subtraction of raw clock hours.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.alignment.config import DEFAULT_ALIGNMENT_CONFIG, AlignmentConfig
from app.alignment.curves import exponential_decay_score
from app.alignment.ideal_sleep import derive_ideal_sleep_onset
from app.synthetic.time_utils import circular_diff_hours


@dataclass(frozen=True)
class PhaseAlignmentResult:
    phase_score: float
    ideal_sleep_onset_hour: float
    actual_sleep_onset_hour: Optional[float]
    phase_deviation_minutes: Optional[float]
    available: bool
    imputed: bool
    notes: str = ""


def compute_phase_alignment(
    fused_dlmo_hour: float,
    actual_sleep_onset_hour: Optional[float],
    fallback_sleep_onset_hour: Optional[float] = None,
    config: AlignmentConfig = DEFAULT_ALIGNMENT_CONFIG,
) -> PhaseAlignmentResult:
    """Compute the phase-alignment score.

    If ``actual_sleep_onset_hour`` is missing, falls back to
    ``fallback_sleep_onset_hour`` (e.g. the most recent available
    sleep onset within the six-day window) and marks the result
    ``imputed``. If neither is available, returns the configured
    neutral fallback score with ``available=False``.
    """

    ideal_sleep_onset_hour = derive_ideal_sleep_onset(fused_dlmo_hour, config)

    onset = actual_sleep_onset_hour
    imputed = False
    if onset is None:
        if fallback_sleep_onset_hour is not None:
            onset = fallback_sleep_onset_hour
            imputed = True
        else:
            return PhaseAlignmentResult(
                phase_score=config.neutral_fallback_score,
                ideal_sleep_onset_hour=ideal_sleep_onset_hour,
                actual_sleep_onset_hour=None,
                phase_deviation_minutes=None,
                available=False,
                imputed=True,
                notes="no sleep onset available (current day or window); neutral fallback score used",
            )

    deviation_minutes = circular_diff_hours(onset, ideal_sleep_onset_hour) * 60.0
    score = exponential_decay_score(deviation_minutes, config.phase_score_decay_minutes)

    return PhaseAlignmentResult(
        phase_score=score,
        ideal_sleep_onset_hour=ideal_sleep_onset_hour,
        actual_sleep_onset_hour=onset,
        phase_deviation_minutes=deviation_minutes,
        available=True,
        imputed=imputed,
        notes="imputed from most recent available window day" if imputed else "",
    )
