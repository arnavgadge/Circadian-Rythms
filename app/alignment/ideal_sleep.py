"""Ideal sleep timing derivation from the fused DLMO.

``ideal_sleep_onset = fused_DLMO + phase_to_sleep_offset`` (a project
modeling assumption, not universally validated physiology -- see
``docs/alignment_engine.md``), computed with circular clock arithmetic
so it wraps correctly across midnight.
"""

from __future__ import annotations

from typing import Optional

from app.alignment.config import DEFAULT_ALIGNMENT_CONFIG, AlignmentConfig
from app.synthetic.time_utils import add_hours


def derive_ideal_sleep_onset(fused_dlmo_hour: float, config: AlignmentConfig = DEFAULT_ALIGNMENT_CONFIG) -> float:
    """The ideal sleep onset hour implied by ``fused_dlmo_hour``."""

    return add_hours(fused_dlmo_hour, config.phase_to_sleep_offset_hours)


def derive_ideal_wake_time(
    ideal_sleep_onset_hour: float, target_sleep_duration_hours: Optional[float]
) -> Optional[float]:
    """``ideal_sleep_onset + target_sleep_duration``, if a target duration
    is available.

    Returns ``None`` when no reliable target sleep duration exists for
    this participant -- deriving the full ideal sleep *window* (not
    just its start) belongs to a later layer once one exists; this
    function deliberately does not invent a universal medical sleep-
    duration recommendation to fill the gap.
    """

    if target_sleep_duration_hours is None:
        return None
    return add_hours(ideal_sleep_onset_hour, target_sleep_duration_hours)
