"""The seven synthetic behavioral personalities.

Personality is independent of chronotype: it describes *how* someone
behaves (consistency, screen habits, meal timing, weekend shift), not
their intrinsic biological phase. Every numeric field on
:class:`PersonalityProfile` is a synthetic modeling choice (see
``app.synthetic.config.SyntheticAssumptions`` and
``docs/synthetic_data_generation.md``) designed to make the seven
personalities produce clearly different behavioral distributions, not
to match any specific published behavioral survey.

All timing fields are expressed as *offsets relative to the
participant's own stable baseline sleep onset* (itself anchored once,
at generation time, to the participant's intrinsic DLMO via the
source-backed sleep-onset/DLMO relationship -- see
``app.synthetic.population``). This keeps every personality's
behavior centered on that participant's own biology while still
producing a personality-specific shape.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PersonalityProfile:
    key: str
    label: str

    # Sleep timing, relative to the participant's baseline sleep onset hour.
    weekday_sleep_onset_shift_hours: float
    weekend_sleep_onset_extra_shift_hours: float  # added on top of the weekday shift on free days
    sleep_duration_mean_hours: float
    sleep_duration_sd_hours: float
    sleep_duration_weekend_extra_hours: float

    # Day-to-day variability and disruption proneness.
    timing_noise_sd_hours: float
    disruption_probability_multiplier: float

    # Morning light.
    morning_light_duration_mean_minutes: float
    morning_light_duration_sd_minutes: float

    # Evening screen, relative to that day's sleep onset (positive =
    # screen ends before sleep onset; negative = screen continues past it).
    evening_screen_duration_mean_hours: float
    evening_screen_duration_sd_hours: float
    evening_screen_end_offset_before_sleep_minutes: float

    # Last meal, relative to that day's sleep onset.
    last_meal_offset_before_sleep_hours_mean: float
    last_meal_offset_before_sleep_hours_sd: float

    # Exercise.
    exercise_time_hour_mean: float
    exercise_time_hour_sd: float
    exercise_duration_minutes_mean: float

    # Caffeine.
    caffeine_time_hour_mean: float
    caffeine_time_hour_sd: float
    caffeine_amount_mg_mean: float


PERSONALITY_PROFILES: dict[str, PersonalityProfile] = {
    "consistent_early_bird": PersonalityProfile(
        key="consistent_early_bird",
        label="Consistent early bird",
        weekday_sleep_onset_shift_hours=-1.0,
        weekend_sleep_onset_extra_shift_hours=0.3,
        sleep_duration_mean_hours=7.8,
        sleep_duration_sd_hours=0.3,
        sleep_duration_weekend_extra_hours=0.0,
        timing_noise_sd_hours=0.25,
        disruption_probability_multiplier=0.5,
        morning_light_duration_mean_minutes=35.0,
        morning_light_duration_sd_minutes=8.0,
        evening_screen_duration_mean_hours=1.0,
        evening_screen_duration_sd_hours=0.4,
        evening_screen_end_offset_before_sleep_minutes=60.0,
        last_meal_offset_before_sleep_hours_mean=3.0,
        last_meal_offset_before_sleep_hours_sd=0.5,
        exercise_time_hour_mean=7.0,
        exercise_time_hour_sd=1.0,
        exercise_duration_minutes_mean=30.0,
        caffeine_time_hour_mean=8.5,
        caffeine_time_hour_sd=1.0,
        caffeine_amount_mg_mean=80.0,
    ),
    "consistent_night_owl": PersonalityProfile(
        key="consistent_night_owl",
        label="Consistent night owl",
        weekday_sleep_onset_shift_hours=1.5,
        weekend_sleep_onset_extra_shift_hours=0.5,
        sleep_duration_mean_hours=7.5,
        sleep_duration_sd_hours=0.4,
        sleep_duration_weekend_extra_hours=0.3,
        timing_noise_sd_hours=0.3,
        disruption_probability_multiplier=0.7,
        morning_light_duration_mean_minutes=10.0,
        morning_light_duration_sd_minutes=5.0,
        evening_screen_duration_mean_hours=3.0,
        evening_screen_duration_sd_hours=0.6,
        evening_screen_end_offset_before_sleep_minutes=-15.0,
        last_meal_offset_before_sleep_hours_mean=1.5,
        last_meal_offset_before_sleep_hours_sd=0.4,
        exercise_time_hour_mean=19.0,
        exercise_time_hour_sd=1.5,
        exercise_duration_minutes_mean=35.0,
        caffeine_time_hour_mean=13.0,
        caffeine_time_hour_sd=2.0,
        caffeine_amount_mg_mean=140.0,
    ),
    "social_jetlag_student": PersonalityProfile(
        key="social_jetlag_student",
        label="Social jetlag student",
        weekday_sleep_onset_shift_hours=0.3,
        weekend_sleep_onset_extra_shift_hours=2.5,
        sleep_duration_mean_hours=6.8,
        sleep_duration_sd_hours=0.5,
        sleep_duration_weekend_extra_hours=1.5,
        timing_noise_sd_hours=0.4,
        disruption_probability_multiplier=1.2,
        morning_light_duration_mean_minutes=15.0,
        morning_light_duration_sd_minutes=8.0,
        evening_screen_duration_mean_hours=2.2,
        evening_screen_duration_sd_hours=0.7,
        evening_screen_end_offset_before_sleep_minutes=0.0,
        last_meal_offset_before_sleep_hours_mean=2.0,
        last_meal_offset_before_sleep_hours_sd=0.6,
        exercise_time_hour_mean=17.0,
        exercise_time_hour_sd=2.0,
        exercise_duration_minutes_mean=25.0,
        caffeine_time_hour_mean=11.0,
        caffeine_time_hour_sd=2.5,
        caffeine_amount_mg_mean=110.0,
    ),
    "chaotic_sleeper": PersonalityProfile(
        key="chaotic_sleeper",
        label="Chaotic sleeper",
        weekday_sleep_onset_shift_hours=0.0,
        weekend_sleep_onset_extra_shift_hours=1.0,
        sleep_duration_mean_hours=7.0,
        sleep_duration_sd_hours=1.2,
        sleep_duration_weekend_extra_hours=0.5,
        timing_noise_sd_hours=1.1,
        disruption_probability_multiplier=2.5,
        morning_light_duration_mean_minutes=15.0,
        morning_light_duration_sd_minutes=12.0,
        evening_screen_duration_mean_hours=2.0,
        evening_screen_duration_sd_hours=1.0,
        evening_screen_end_offset_before_sleep_minutes=0.0,
        last_meal_offset_before_sleep_hours_mean=2.0,
        last_meal_offset_before_sleep_hours_sd=1.0,
        exercise_time_hour_mean=16.0,
        exercise_time_hour_sd=4.0,
        exercise_duration_minutes_mean=20.0,
        caffeine_time_hour_mean=12.0,
        caffeine_time_hour_sd=3.0,
        caffeine_amount_mg_mean=100.0,
    ),
    "healthy_stable_routine": PersonalityProfile(
        key="healthy_stable_routine",
        label="Healthy stable routine",
        weekday_sleep_onset_shift_hours=-0.3,
        weekend_sleep_onset_extra_shift_hours=0.2,
        sleep_duration_mean_hours=7.7,
        sleep_duration_sd_hours=0.25,
        sleep_duration_weekend_extra_hours=0.0,
        timing_noise_sd_hours=0.2,
        disruption_probability_multiplier=0.4,
        morning_light_duration_mean_minutes=30.0,
        morning_light_duration_sd_minutes=6.0,
        evening_screen_duration_mean_hours=1.2,
        evening_screen_duration_sd_hours=0.3,
        evening_screen_end_offset_before_sleep_minutes=75.0,
        last_meal_offset_before_sleep_hours_mean=3.2,
        last_meal_offset_before_sleep_hours_sd=0.4,
        exercise_time_hour_mean=7.5,
        exercise_time_hour_sd=1.0,
        exercise_duration_minutes_mean=40.0,
        caffeine_time_hour_mean=8.5,
        caffeine_time_hour_sd=1.0,
        caffeine_amount_mg_mean=90.0,
    ),
    "screen_heavy_user": PersonalityProfile(
        key="screen_heavy_user",
        label="Screen-heavy user",
        weekday_sleep_onset_shift_hours=0.3,
        weekend_sleep_onset_extra_shift_hours=0.8,
        sleep_duration_mean_hours=7.2,
        sleep_duration_sd_hours=0.5,
        sleep_duration_weekend_extra_hours=0.3,
        timing_noise_sd_hours=0.35,
        disruption_probability_multiplier=0.8,
        morning_light_duration_mean_minutes=18.0,
        morning_light_duration_sd_minutes=8.0,
        evening_screen_duration_mean_hours=3.8,
        evening_screen_duration_sd_hours=0.8,
        evening_screen_end_offset_before_sleep_minutes=-20.0,
        last_meal_offset_before_sleep_hours_mean=2.2,
        last_meal_offset_before_sleep_hours_sd=0.5,
        exercise_time_hour_mean=18.0,
        exercise_time_hour_sd=2.0,
        exercise_duration_minutes_mean=25.0,
        caffeine_time_hour_mean=11.0,
        caffeine_time_hour_sd=2.0,
        caffeine_amount_mg_mean=100.0,
    ),
    "late_eater": PersonalityProfile(
        key="late_eater",
        label="Late eater",
        weekday_sleep_onset_shift_hours=0.0,
        weekend_sleep_onset_extra_shift_hours=0.5,
        sleep_duration_mean_hours=7.3,
        sleep_duration_sd_hours=0.4,
        sleep_duration_weekend_extra_hours=0.2,
        timing_noise_sd_hours=0.3,
        disruption_probability_multiplier=0.7,
        morning_light_duration_mean_minutes=20.0,
        morning_light_duration_sd_minutes=8.0,
        evening_screen_duration_mean_hours=1.8,
        evening_screen_duration_sd_hours=0.5,
        evening_screen_end_offset_before_sleep_minutes=45.0,
        last_meal_offset_before_sleep_hours_mean=0.7,
        last_meal_offset_before_sleep_hours_sd=0.3,
        exercise_time_hour_mean=17.5,
        exercise_time_hour_sd=2.0,
        exercise_duration_minutes_mean=25.0,
        caffeine_time_hour_mean=11.0,
        caffeine_time_hour_sd=2.0,
        caffeine_amount_mg_mean=95.0,
    ),
}
