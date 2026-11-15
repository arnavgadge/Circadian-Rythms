"""Deterministic 30-day behavioral generator for DEMO-001.

Produces **raw behavioral observations only** -- sleep, light, screens,
meals, exercise, caffeine -- for a synthetic research participant.
It computes no DLMO, alignment, contributor, recommendation, or any
other derived CircadianIQ result; those come exclusively from the
existing pipeline when ``seed_demo_participant.py`` runs it.

Design:

* One ``random.Random(seed)`` stream -- same seed, same 30 days, on any
  machine. No numpy, no wall-clock input.
* Four behavioral periods (days 1-7 baseline, 8-14 analysis, 15-21
  adjustment, 22-30 continued observation). Each period only shifts the
  *means* the participant's habits are drawn around; daily values keep
  their own noise, and a few named setback days revert toward baseline,
  so the improvement is partial and uneven, never a clean ramp.
* Free days follow the project's own convention (Saturday/Sunday,
  ``SyntheticAssumptions.free_day_weekday_indices``) and get later,
  longer sleep.
* Stored derived-raw columns (sleep midpoint, free-day midpoint, social
  jetlag, meal-to-sleep gap) use the same definitions as the existing
  synthetic generator (``app.synthetic.behavior.generate_daily_behavior``)
  so DEMO-001's rows look like every other synthetic participant's.
* The participant's intrinsic DLMO -- the one profile trait inference
  requires -- is drawn from the project's source-backed chronotype
  distribution (``SourceBackedAssumptions.dlmo_mean_hour_by_chronotype``)
  with the same seeded stream, and the habitual sleep onset follows the
  project's ``sleep_onset_after_dlmo_hours`` convention. Nothing here
  picks a DLMO by hand.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from datetime import date as date_cls, timedelta
from typing import Optional

from app.synthetic.config import DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC
from app.synthetic.time_utils import circular_diff_minutes, normalize_hour

GENERATOR_VERSION = "demo-001-generator/1.0.0"
DEFAULT_SEED = 20261005
DEFAULT_START_DATE = date_cls(2026, 10, 5)  # a Monday: free days fall on real weekends
NUM_DAYS = 30
CHRONOTYPE = "intermediate"  # key into the source-backed chronotype tables

# Day numbers (1-based) where the participant slips back toward baseline
# habits during the improvement periods -- realistic setbacks.
SETBACK_DAYS = frozenset({17, 20, 26})


@dataclass(frozen=True)
class PersonaTraits:
    chronotype_label: str  # as stored in participant_profiles.chronotype_category
    intrinsic_dlmo_hour: float
    habitual_sleep_onset_hour: float  # intrinsic + sleep_onset_after_dlmo_hours
    weekday_sleep_duration_hours: float


@dataclass(frozen=True)
class PeriodPlan:
    name: str
    onset_shift_min: float  # vs. habitual onset, weekdays
    onset_sd_min: float
    light_mean_min: float
    light_sd_min: float
    light_skip_prob: float  # chance of no morning light at all
    screen_end_before_onset_min: float  # how long before sleep screens stop
    screen_duration_mean_min: float
    meal_mean_hour: float
    meal_sd_min: float
    caffeine_mean_hour: float


PERIODS = {
    "baseline": PeriodPlan("baseline", 55, 45, 10, 8, 0.30, 10, 205, 21.75, 40, 16.75),
    "analysis": PeriodPlan("analysis", 40, 38, 16, 9, 0.20, 25, 180, 21.50, 35, 16.25),
    "adjustment": PeriodPlan("adjustment", 15, 30, 27, 10, 0.05, 55, 140, 20.90, 30, 15.25),
    "continued": PeriodPlan("continued", 5, 25, 31, 9, 0.0, 70, 120, 20.60, 25, 14.50),
}


def period_for_day(day: int) -> str:
    if day <= 7:
        return "baseline"
    if day <= 14:
        return "analysis"
    if day <= 21:
        return "adjustment"
    return "continued"


@dataclass(frozen=True)
class GeneratedDay:
    day: int
    observation_date: str  # ISO date
    period: str
    setback: bool
    is_free_day: bool
    sleep_onset_time: str
    sleep_offset_time: str
    sleep_duration_minutes: float
    sleep_midpoint_time: str
    sleep_midpoint_variability_minutes: Optional[float]
    free_day_sleep_onset_time: Optional[str]
    free_day_sleep_offset_time: Optional[str]
    free_day_sleep_midpoint_time: Optional[str]
    social_jetlag_minutes: Optional[float]
    morning_light_start_time: str
    morning_light_duration_minutes: float
    evening_screen_end_time: str
    evening_screen_duration_minutes: float
    last_meal_time: str
    meal_to_sleep_gap_minutes: float
    exercise_time: str
    exercise_duration_minutes: float
    last_caffeine_time: str
    caffeine_amount_mg: float


def _round_to(hour: float, step_minutes: int = 5) -> float:
    total = round(normalize_hour(hour) * 60 / step_minutes) * step_minutes
    return (total % (24 * 60)) / 60.0


def _hhmm(hour: float) -> str:
    total = int(round(normalize_hour(hour) * 60)) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def draw_persona(rng: random.Random) -> PersonaTraits:
    mean = DEFAULT_SOURCE_BACKED.dlmo_mean_hour_by_chronotype[CHRONOTYPE]
    sd = DEFAULT_SOURCE_BACKED.dlmo_sd_hours_by_chronotype[CHRONOTYPE]
    intrinsic = _round_to(rng.gauss(mean, sd))
    habitual = _round_to(intrinsic + DEFAULT_SOURCE_BACKED.sleep_onset_after_dlmo_hours)
    return PersonaTraits(
        chronotype_label=CHRONOTYPE.capitalize(),
        intrinsic_dlmo_hour=intrinsic,
        habitual_sleep_onset_hour=habitual,
        weekday_sleep_duration_hours=7.0,
    )


def generate(seed: int = DEFAULT_SEED, start_date: date_cls = DEFAULT_START_DATE) -> tuple[PersonaTraits, list[GeneratedDay]]:
    rng = random.Random(seed)
    persona = draw_persona(rng)

    # Social-jetlag reference: the planned weekday sleep midpoint (same
    # construction as app.synthetic.behavior's reference_weekday_midpoint).
    reference_weekday_midpoint = normalize_hour(persona.habitual_sleep_onset_hour + persona.weekday_sleep_duration_hours / 2.0)

    days: list[GeneratedDay] = []
    previous_midpoint: Optional[float] = None
    for day in range(1, NUM_DAYS + 1):
        obs_date = start_date + timedelta(days=day - 1)
        setback = day in SETBACK_DAYS
        period_name = period_for_day(day)
        plan = PERIODS["baseline" if setback else period_name]
        free_day = obs_date.weekday() in DEFAULT_SYNTHETIC.free_day_weekday_indices

        # --- sleep ---
        onset_shift = plan.onset_shift_min + (55 if free_day else 0)
        onset = _round_to(persona.habitual_sleep_onset_hour + (onset_shift + rng.gauss(0, plan.onset_sd_min)) / 60.0)
        duration_h = persona.weekday_sleep_duration_hours + (0.9 if free_day else 0.0) + rng.gauss(0, 0.45)
        duration_min = float(max(270, min(600, round(duration_h * 60 / 5) * 5)))
        offset = _round_to(onset + duration_min / 60.0)
        midpoint = normalize_hour(onset + duration_min / 120.0)
        variability = abs(circular_diff_minutes(midpoint, previous_midpoint)) if previous_midpoint is not None else None
        previous_midpoint = midpoint
        social_jetlag = abs(circular_diff_minutes(midpoint, reference_weekday_midpoint)) if free_day else None

        # --- morning light: starts after waking ---
        light_start = _round_to(offset + max(10.0, rng.gauss(40 if free_day else 25, 15)) / 60.0)
        light = 0.0 if rng.random() < plan.light_skip_prob else max(0.0, round(rng.gauss(plan.light_mean_min, plan.light_sd_min)))

        # --- evening screens: end shortly before sleep onset ---
        screen_end = _round_to(onset - max(0.0, rng.gauss(plan.screen_end_before_onset_min, 12)) / 60.0)
        screen_duration = float(max(20, round(rng.gauss(plan.screen_duration_mean_min, 25) / 5) * 5))

        # --- meals ---
        meal = _round_to(plan.meal_mean_hour + (0.5 if free_day else 0.0) + rng.gauss(0, plan.meal_sd_min) / 60.0)
        meal_gap = circular_diff_minutes(onset, meal)  # minutes from last meal to sleep onset
        if meal_gap < 0:
            meal_gap += 24 * 60
        meal_gap = round(meal_gap)

        # --- exercise: evenings early on, more mornings later ---
        morning_ex_prob = {"baseline": 0.15, "analysis": 0.3, "adjustment": 0.5, "continued": 0.6}[period_name if not setback else "baseline"]
        exercise = _round_to((7.0 + rng.gauss(0, 0.5)) if rng.random() < morning_ex_prob else (19.25 + rng.gauss(0, 0.75)))
        exercise_duration = float(round(rng.uniform(25, 55) / 5) * 5)

        # --- caffeine ---
        caffeine = _round_to(plan.caffeine_mean_hour + rng.gauss(0, 0.75))
        caffeine_mg = float(round(rng.gauss(150, 40) / 10) * 10)
        caffeine_mg = max(40.0, min(320.0, caffeine_mg))

        days.append(
            GeneratedDay(
                day=day,
                observation_date=obs_date.isoformat(),
                period=period_name,
                setback=setback,
                is_free_day=free_day,
                sleep_onset_time=_hhmm(onset),
                sleep_offset_time=_hhmm(offset),
                sleep_duration_minutes=duration_min,
                sleep_midpoint_time=_hhmm(midpoint),
                sleep_midpoint_variability_minutes=round(variability, 1) if variability is not None else None,
                free_day_sleep_onset_time=_hhmm(onset) if free_day else None,
                free_day_sleep_offset_time=_hhmm(offset) if free_day else None,
                free_day_sleep_midpoint_time=_hhmm(midpoint) if free_day else None,
                social_jetlag_minutes=round(social_jetlag, 1) if social_jetlag is not None else None,
                morning_light_start_time=_hhmm(light_start),
                morning_light_duration_minutes=float(light),
                evening_screen_end_time=_hhmm(screen_end),
                evening_screen_duration_minutes=screen_duration,
                last_meal_time=_hhmm(meal),
                meal_to_sleep_gap_minutes=float(meal_gap),
                exercise_time=_hhmm(exercise),
                exercise_duration_minutes=exercise_duration,
                last_caffeine_time=_hhmm(caffeine),
                caffeine_amount_mg=caffeine_mg,
            )
        )
    return persona, days


def dataset_checksum(persona: PersonaTraits, days: list[GeneratedDay]) -> str:
    """SHA-256 over the canonical JSON of the persona + all 30 days."""

    payload = json.dumps({"persona": asdict(persona), "days": [asdict(d) for d in days]}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
