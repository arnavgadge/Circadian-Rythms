"""Configuration for the CircadianIQ feature engineering layer.

Every non-obvious numeric constant used anywhere in ``app.features``
lives here, explicitly labeled. None of it is claimed to be
clinically or biologically validated -- see
``docs/feature_engineering.md`` section "Assumptions" for the full
discussion. This mirrors the source-backed/synthetic split used in
``app.synthetic.config`` for Phase 3, except almost nothing in feature
*engineering* (as opposed to data *generation*) has a literature
source at all: recency weighting schemes, imputation defaults, and the
MEQ->expected-phase mapping used for the MEQ/MSFsc divergence feature
are all modeling choices made for this project, not cited findings.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FeatureConfig:
    """Tunable parameters for feature construction."""

    window_size_days: int = 6

    # --- Recency weighting ---
    # Linear weights favoring the most recent day, oldest to newest:
    # day_1 (oldest) gets weight 1, day_6 (most recent) gets weight 6,
    # normalized to sum to 1 inside `recency_weighted_mean`. This is a
    # simple, explicit, configurable choice -- not a fitted or
    # biologically validated decay constant. Change it here, in one
    # place, if a different scheme is ever adopted.
    recency_weights: tuple = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0)

    # --- MEQ ---
    meq_min: int = 16
    meq_max: int = 86

    # --- MEQ -> expected free-day phase mapping (for MEQ/MSFsc divergence) ---
    # A synthetic, monotonic mapping from MEQ score to an "expected"
    # free-day sleep-midpoint hour: higher MEQ (more morning-type) maps
    # to an earlier expected midpoint, lower MEQ (more evening-type) to
    # a later one. The two anchor hours below are illustrative, chosen
    # to sit in a plausible free-day mid-sleep range; they are NOT
    # derived from a validated MEQ-to-MSFsc regression. This is exactly
    # the "modeling assumption" the project brief calls out explicitly.
    meq_morning_type_msfsc_hour: float = 2.5  # expected MSFsc at MEQ = meq_max
    meq_evening_type_msfsc_hour: float = 6.5  # expected MSFsc at MEQ = meq_min

    # --- Population-default imputation fallbacks ---
    # Used only when a signal is missing for every day in a window AND
    # the participant has no usable personal history before the window
    # (e.g. the participant's very first window). Plain, round,
    # documented defaults -- not statistics fit from the dataset itself
    # (which would make "population default" behavior depend on
    # generation order) and not claimed to be biologically typical.
    default_screen_end_hour: float = 23.0
    default_last_meal_hour: float = 20.5
    default_morning_light_start_hour: float = 7.5
    default_exercise_time_hour: float = 18.0
    default_msfsc_hour: float = 4.5

    default_sleep_duration_hours: float = 7.5
    default_sleep_midpoint_variability_minutes: float = 30.0
    default_screen_duration_hours: float = 2.0
    default_morning_light_duration_minutes: float = 20.0
    default_exercise_duration_minutes: float = 25.0
    default_exercise_frequency_ratio: float = 0.4
    default_caffeine_amount_mg: float = 100.0
    default_social_jetlag_minutes: float = 60.0
    default_free_day_ratio: float = 2.0 / 7.0
    default_meq_score: float = 50.0

    # --- Missing-data signal tiers (Q25 architecture, feature-engineering half) ---
    tier_1_signals: tuple = ("msfsc", "evening_screen_end", "morning_light_start")
    tier_2_signals: tuple = ("last_meal", "social_jetlag", "meq")
    tier_3_signals: tuple = ("exercise", "caffeine", "sleep_midpoint_variability")


DEFAULT_FEATURE_CONFIG = FeatureConfig()
