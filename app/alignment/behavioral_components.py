"""The five behavioral-alignment components.

Each function follows the same contract
(:class:`app.alignment.inputs.ComponentScore`): a 0-100 score, the raw
value(s) it was computed from, a target/reference where one exists, a
deviation where one exists, and explicit availability/imputation
bookkeeping. All five operate on the **six-day window**, not a single
day (see ``docs/alignment_engine.md`` "Time horizons") -- so one
anomalous night does not by itself swing the behavioral score.

Tier classification for morning light / evening screen / meal timing
reuses the exact classifiers already established in
``app.state.behavioral_effect`` (which themselves reuse
``app.synthetic.config.SyntheticAssumptions`` thresholds) -- this
module only assigns a *score* to each tier, never redefines the tier
boundaries.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

from app.alignment.config import DEFAULT_ALIGNMENT_CONFIG, AlignmentConfig
from app.alignment.curves import exponential_decay_score, tier_score
from app.alignment.inputs import ComponentScore
from app.state.behavioral_effect import evening_screen_tier, last_meal_tier, morning_light_tier
from app.synthetic.config import DEFAULT_SYNTHETIC
from app.synthetic.time_utils import circular_std_hours


def _is_missing(value) -> bool:
    """True for ``None`` or NaN. Callers may source window values from a
    database (``NULL`` -> ``None``) or from a pandas DataFrame (missing
    -> ``float('nan')``); ``value is not None`` alone silently lets NaN
    through, poisoning any downstream mean/std with NaN. Both must be
    treated as "missing" here.
    """

    return value is None or (isinstance(value, float) and math.isnan(value))


def _present(values: Sequence) -> list:
    return [v for v in values if not _is_missing(v)]


def compute_sleep_consistency_score(
    window_sleep_onset_hours: Sequence, config: AlignmentConfig = DEFAULT_ALIGNMENT_CONFIG
) -> ComponentScore:
    """Reward *regularity* of sleep-onset timing, not any particular
    clock time -- a consistently-early and a consistently-late sleeper
    can both score near 100; a highly variable sleeper of either
    chronotype scores low.
    """

    present = _present(window_sleep_onset_hours)
    if len(present) < 2:
        return ComponentScore(
            name="sleep_consistency", score=config.neutral_fallback_score,
            available=False, imputed=True, notes="fewer than 2 sleep-onset observations in window",
        )

    variability_hours = circular_std_hours(present)
    variability_minutes = variability_hours * 60.0
    score = exponential_decay_score(variability_minutes, config.sleep_consistency_decay_minutes)
    imputed = len(present) < len(window_sleep_onset_hours)

    return ComponentScore(
        name="sleep_consistency", score=score, raw_value=variability_minutes, target=0.0,
        deviation=variability_minutes, available=True, imputed=imputed,
        notes=f"circular std of {len(present)}/{len(window_sleep_onset_hours)} window sleep-onset observations",
    )


def compute_morning_light_score(
    window_morning_light_duration_minutes: Sequence, config: AlignmentConfig = DEFAULT_ALIGNMENT_CONFIG
) -> ComponentScore:
    present = _present(window_morning_light_duration_minutes)
    if not present:
        return ComponentScore(
            name="morning_light", score=config.neutral_fallback_score,
            available=False, imputed=True, notes="no morning-light observations in window",
        )

    mean_duration = sum(present) / len(present)
    tier = morning_light_tier(mean_duration, DEFAULT_SYNTHETIC)
    score = tier_score(tier, config.morning_light_tier_scores, config.neutral_fallback_score)
    imputed = len(present) < len(window_morning_light_duration_minutes)

    return ComponentScore(
        name="morning_light", score=score, raw_value=mean_duration, target=None, deviation=None,
        available=True, imputed=imputed, notes=f"tier={tier}, mean of {len(present)} window days",
    )


def compute_evening_screen_score(
    window_evening_screen_duration_hours: Sequence, config: AlignmentConfig = DEFAULT_ALIGNMENT_CONFIG
) -> ComponentScore:
    present = _present(window_evening_screen_duration_hours)
    if not present:
        return ComponentScore(
            name="evening_screen", score=config.neutral_fallback_score,
            available=False, imputed=True, notes="no evening-screen observations in window",
        )

    mean_duration = sum(present) / len(present)
    tier = evening_screen_tier(mean_duration, DEFAULT_SYNTHETIC)
    score = tier_score(tier, config.evening_screen_tier_scores, config.neutral_fallback_score)
    imputed = len(present) < len(window_evening_screen_duration_hours)

    return ComponentScore(
        name="evening_screen", score=score, raw_value=mean_duration, target=None, deviation=None,
        available=True, imputed=imputed, notes=f"tier={tier}, mean of {len(present)} window days",
    )


def compute_meal_timing_score(
    window_last_meal_hours: Sequence, config: AlignmentConfig = DEFAULT_ALIGNMENT_CONFIG
) -> ComponentScore:
    present = _present(window_last_meal_hours)
    if not present:
        return ComponentScore(
            name="meal_timing", score=config.neutral_fallback_score,
            available=False, imputed=True, notes="no last-meal observations in window",
        )

    # Circular mean is unnecessary here (meal times cluster well away
    # from midnight in practice), but a plain mean of clock hours would
    # still be safe for the typical evening range this represents; kept
    # simple and documented rather than importing circular-mean machinery
    # for a signal that does not, in practice, straddle the wrap point.
    mean_hour = sum(present) / len(present)
    tier = last_meal_tier(mean_hour, DEFAULT_SYNTHETIC)
    score = tier_score(tier, config.meal_timing_tier_scores, config.neutral_fallback_score)
    imputed = len(present) < len(window_last_meal_hours)

    return ComponentScore(
        name="meal_timing", score=score, raw_value=mean_hour, target=None, deviation=None,
        available=True, imputed=imputed, notes=f"tier={tier}, mean of {len(present)} window days",
    )


def compute_social_jetlag_score(
    window_social_jetlag_minutes: Sequence, config: AlignmentConfig = DEFAULT_ALIGNMENT_CONFIG
) -> ComponentScore:
    """Social jetlag is only ever recorded on free days (Phase 3/4); a
    window with no free days at all has no jetlag observations, which
    is a data-*availability* gap, not evidence of zero jetlag.
    """

    present = _present(window_social_jetlag_minutes)
    if not present:
        return ComponentScore(
            name="social_jetlag", score=config.neutral_fallback_score,
            available=False, imputed=True, notes="no free days with recorded social jetlag in window",
        )

    mean_jetlag_minutes = sum(present) / len(present)
    score = exponential_decay_score(mean_jetlag_minutes / 60.0, config.social_jetlag_decay_hours)

    return ComponentScore(
        name="social_jetlag", score=score, raw_value=mean_jetlag_minutes, target=0.0,
        deviation=mean_jetlag_minutes, available=True, imputed=False,
        notes=f"mean of {len(present)} free-day observations in window",
    )
