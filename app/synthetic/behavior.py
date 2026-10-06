"""Independent daily behavior generation.

Behavior is generated as: **personality baseline + weekday/weekend
effect + day-level stochastic noise + occasional disruption**. It
never reads the participant's evolving ``current_DLMO`` -- doing so
would create a behavior -> biology -> behavior feedback loop that
would make the resulting dataset circular and useless for later
supervised learning (the whole point of Phase 4/5 is to predict DLMO
*from* behavior). The only biological quantity behavior generation is
allowed to depend on is the participant's stable, non-evolving
``baseline_sleep_onset_hour`` trait, itself fixed once at onboarding
(see ``app.synthetic.population``) from the *intrinsic* DLMO -- never
from the day-to-day state.

Fields that are genuinely windowed/aggregate quantities (free-day
ratio, multi-day sleep variability, MSFsc itself) are deliberately
**not** computed here; only what a single day, plus the immediately
preceding day where noted, can determine. Windowing is Phase 4's job.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_cls
from typing import Optional

import numpy as np

from app.synthetic.config import SyntheticAssumptions
from app.synthetic.personalities import PersonalityProfile
from app.synthetic.population import ParticipantTraits
from app.synthetic.time_utils import circular_diff_minutes, normalize_hour


@dataclass
class DailyBehaviorRecord:
    day_index: int
    date: date_cls
    is_free_day: bool
    had_disruption: bool

    sleep_onset_hour: float
    sleep_offset_hour: float
    sleep_duration_hours: float
    sleep_midpoint_hour: float
    sleep_midpoint_variability_minutes: Optional[float]

    free_day_sleep_onset_hour: Optional[float]
    free_day_sleep_offset_hour: Optional[float]
    free_day_sleep_midpoint_hour: Optional[float]
    social_jetlag_minutes: Optional[float]

    morning_light_start_hour: float
    morning_light_duration_minutes: float

    evening_screen_end_hour: float
    evening_screen_duration_hours: float

    last_meal_hour: float
    meal_to_sleep_gap_minutes: float

    exercise_hour: float
    exercise_duration_minutes: float

    caffeine_hour: float
    caffeine_amount_mg: float

    resting_hr_bpm: float
    hrv_ms: float
    wrist_temp_c: float


def is_free_day(date_obj: date_cls, synthetic: SyntheticAssumptions) -> bool:
    return date_obj.weekday() in synthetic.free_day_weekday_indices


def generate_daily_behavior(
    participant: ParticipantTraits,
    personality: PersonalityProfile,
    day_index: int,
    date_obj: date_cls,
    behavior_rng: np.random.Generator,
    disruption_rng: np.random.Generator,
    physiology_rng: np.random.Generator,
    synthetic: SyntheticAssumptions,
    previous_sleep_midpoint_hour: Optional[float],
) -> DailyBehaviorRecord:
    """Generate one day of raw behavioral + physiological observations.

    ``behavior_rng``/``disruption_rng``/``physiology_rng`` are expected
    to be the same per-participant stream objects across all 30 days
    (advanced sequentially day by day), so draws are reproducible
    without being coupled to other participants' draws.
    """

    free_day = is_free_day(date_obj, synthetic)

    # --- Sleep timing ---
    shift = personality.weekday_sleep_onset_shift_hours
    if free_day:
        shift += personality.weekend_sleep_onset_extra_shift_hours

    mean_onset = participant.baseline_sleep_onset_hour + shift
    day_noise = behavior_rng.normal(0.0, personality.timing_noise_sd_hours)

    had_disruption = bool(
        disruption_rng.random() < synthetic.disruption_probability * personality.disruption_probability_multiplier
    )
    disruption_shift = 0.0
    if had_disruption:
        magnitude = disruption_rng.uniform(*synthetic.disruption_magnitude_hours_range)
        sign = disruption_rng.choice([-1.0, 1.0])
        disruption_shift = sign * magnitude

    sleep_onset_hour = normalize_hour(mean_onset + day_noise + disruption_shift)

    duration_mean = personality.sleep_duration_mean_hours
    if free_day:
        duration_mean += personality.sleep_duration_weekend_extra_hours
    sleep_duration_hours = float(
        np.clip(behavior_rng.normal(duration_mean, personality.sleep_duration_sd_hours), 3.0, 11.0)
    )

    sleep_offset_hour = normalize_hour(sleep_onset_hour + sleep_duration_hours)
    sleep_midpoint_hour = normalize_hour(sleep_onset_hour + sleep_duration_hours / 2.0)

    sleep_midpoint_variability_minutes: Optional[float] = None
    if previous_sleep_midpoint_hour is not None:
        sleep_midpoint_variability_minutes = abs(
            circular_diff_minutes(sleep_midpoint_hour, previous_sleep_midpoint_hour)
        )

    free_day_sleep_onset_hour = sleep_onset_hour if free_day else None
    free_day_sleep_offset_hour = sleep_offset_hour if free_day else None
    free_day_sleep_midpoint_hour = sleep_midpoint_hour if free_day else None

    social_jetlag_minutes: Optional[float] = None
    if free_day:
        reference_weekday_midpoint = normalize_hour(
            participant.baseline_sleep_onset_hour
            + personality.weekday_sleep_onset_shift_hours
            + personality.sleep_duration_mean_hours / 2.0
        )
        social_jetlag_minutes = abs(
            circular_diff_minutes(sleep_midpoint_hour, reference_weekday_midpoint)
        )

    # --- Morning light: starts shortly after waking ---
    wake_offset_minutes = behavior_rng.normal(20.0, 10.0)
    morning_light_start_hour = normalize_hour(sleep_offset_hour + wake_offset_minutes / 60.0)
    morning_light_duration_minutes = float(
        np.clip(
            behavior_rng.normal(
                personality.morning_light_duration_mean_minutes,
                personality.morning_light_duration_sd_minutes,
            ),
            0.0,
            120.0,
        )
    )

    # --- Evening screen: anchored to that day's sleep onset ---
    evening_screen_end_hour = normalize_hour(
        sleep_onset_hour - personality.evening_screen_end_offset_before_sleep_minutes / 60.0
    )
    evening_screen_duration_hours = float(
        np.clip(
            behavior_rng.normal(
                personality.evening_screen_duration_mean_hours,
                personality.evening_screen_duration_sd_hours,
            ),
            0.0,
            8.0,
        )
    )

    # --- Last meal: anchored to that day's sleep onset ---
    meal_offset_hours = float(
        np.clip(
            behavior_rng.normal(
                personality.last_meal_offset_before_sleep_hours_mean,
                personality.last_meal_offset_before_sleep_hours_sd,
            ),
            0.1,
            8.0,
        )
    )
    last_meal_hour = normalize_hour(sleep_onset_hour - meal_offset_hours)
    meal_to_sleep_gap_minutes = meal_offset_hours * 60.0

    # --- Exercise ---
    exercise_hour = normalize_hour(
        behavior_rng.normal(personality.exercise_time_hour_mean, personality.exercise_time_hour_sd)
    )
    exercise_duration_minutes = float(
        max(0.0, behavior_rng.normal(personality.exercise_duration_minutes_mean, 10.0))
    )

    # --- Caffeine ---
    caffeine_hour = normalize_hour(
        behavior_rng.normal(personality.caffeine_time_hour_mean, personality.caffeine_time_hour_sd)
    )
    caffeine_amount_mg = float(
        np.clip(behavior_rng.normal(personality.caffeine_amount_mg_mean, 30.0), 0.0, 600.0)
    )

    # --- Physiology: synthetic, noisy, and NOT a causal DLMO input ---
    resting_hr_bpm = float(np.clip(physiology_rng.normal(62.0, 7.0), 40.0, 110.0))
    hrv_ms = float(np.clip(physiology_rng.normal(55.0, 15.0), 10.0, 150.0))
    wrist_temp_c = float(np.clip(physiology_rng.normal(33.5, 0.4), 30.0, 38.0))

    return DailyBehaviorRecord(
        day_index=day_index,
        date=date_obj,
        is_free_day=free_day,
        had_disruption=had_disruption,
        sleep_onset_hour=sleep_onset_hour,
        sleep_offset_hour=sleep_offset_hour,
        sleep_duration_hours=sleep_duration_hours,
        sleep_midpoint_hour=sleep_midpoint_hour,
        sleep_midpoint_variability_minutes=sleep_midpoint_variability_minutes,
        free_day_sleep_onset_hour=free_day_sleep_onset_hour,
        free_day_sleep_offset_hour=free_day_sleep_offset_hour,
        free_day_sleep_midpoint_hour=free_day_sleep_midpoint_hour,
        social_jetlag_minutes=social_jetlag_minutes,
        morning_light_start_hour=morning_light_start_hour,
        morning_light_duration_minutes=morning_light_duration_minutes,
        evening_screen_end_hour=evening_screen_end_hour,
        evening_screen_duration_hours=evening_screen_duration_hours,
        last_meal_hour=last_meal_hour,
        meal_to_sleep_gap_minutes=meal_to_sleep_gap_minutes,
        exercise_hour=exercise_hour,
        exercise_duration_minutes=exercise_duration_minutes,
        caffeine_hour=caffeine_hour,
        caffeine_amount_mg=caffeine_amount_mg,
        resting_hr_bpm=resting_hr_bpm,
        hrv_ms=hrv_ms,
        wrist_temp_c=wrist_temp_c,
    )
