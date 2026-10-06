"""The single authoritative behavioral-effect model.

This is the same effect model Phase 3's synthetic generator uses (light
/ screen / meal / exercise / caffeine, with the three documented
interaction rules) -- moved here so there is exactly one implementation
shared by simulation and by the state engine, per the Phase 6
requirement not to maintain two copies that can silently drift apart.
``app.synthetic.dlmo_state`` now delegates to this module instead of
computing its own copy (see that module's docstring).

The curve anchors and interaction multipliers are **not** redefined
here: they are imported directly from ``app.synthetic.config``
(:class:`~app.synthetic.config.SourceBackedAssumptions` and
:class:`~app.synthetic.config.SyntheticAssumptions`), which already
carries the source-backed-vs-synthetic citation labeling established
in Phase 3. Reusing those objects (rather than copying their values)
is what guarantees this module can never silently disagree with
Phase 3 about what a given behavior's effect should be.

Sign convention: positive minutes = phase delay (later); negative =
phase advance (earlier).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.synthetic.config import SourceBackedAssumptions, SyntheticAssumptions
from app.synthetic.time_utils import circular_diff_hours


@dataclass(frozen=True)
class DailyBehaviorInputs:
    """The minimal interpretable daily behavior the effect model needs."""

    morning_light_duration_minutes: float
    evening_screen_duration_hours: float
    last_meal_hour: float
    exercise_hour: float
    caffeine_hour: float
    caffeine_amount_mg: float


@dataclass(frozen=True)
class BehavioralEffect:
    """The interpretable breakdown of one day's behavioral phase influence.

    ``light_effect``/``screen_effect``/``meal_effect``/``exercise_effect``/
    ``caffeine_effect`` are each participant-sensitivity-scaled, **final**
    per-signal values -- i.e. ``screen_effect`` and ``meal_effect``
    already include whatever the interaction rules did to them.
    ``interaction_effect`` is a separate *diagnostic* summary: the
    combined delta the interaction rules contributed on top of the
    pre-interaction (raw) screen/meal values (``final - raw``, summed).
    It is informational, not an additional term to add on top of the
    other five -- ``total_shift`` is simply
    ``light + screen + meal + exercise + caffeine`` (plus any
    simulation-time noise), clipped to the configured bound.
    """

    light_effect: float
    screen_effect: float
    meal_effect: float
    exercise_effect: float
    caffeine_effect: float
    interaction_effect: float
    total_shift: float
    morning_light_tier: str
    evening_screen_tier: str
    last_meal_tier: str


def classify_tier(value: float, thresholds: tuple, labels: tuple) -> str:
    """Generic ascending-threshold tier classifier (see Phase 3's identical
    helper -- reused conceptually, kept local to avoid a needless
    cross-package import for one small function)."""

    for i, threshold in enumerate(thresholds):
        if value < threshold:
            return labels[i]
    return labels[-1]


def morning_light_tier(duration_minutes: float, synthetic: SyntheticAssumptions) -> str:
    return classify_tier(duration_minutes, synthetic.morning_light_tier_minutes[1:], synthetic.morning_light_tier_labels)


def evening_screen_tier(duration_hours: float, synthetic: SyntheticAssumptions) -> str:
    return classify_tier(duration_hours, synthetic.evening_screen_tier_hours[1:], synthetic.evening_screen_tier_labels)


def last_meal_tier(last_meal_hour: float, synthetic: SyntheticAssumptions) -> str:
    """Classify a last-meal clock hour into a tier.

    ``synthetic.last_meal_tier_hours`` thresholds (20/21/22/23) are all
    evening clock hours, so a last-meal hour must be compared on the
    same "shifted" evening/night axis used elsewhere for this exact
    wraparound (see ``app.synthetic.diagnostics._shift_late_night``):
    clock hours before noon are actually post-midnight continuations of
    the previous evening (e.g. a 00:30 last meal is later, not earlier,
    than a 23:30 one) and must be shifted by +24h before thresholding --
    otherwise a post-midnight meal naively compares as "less than 20"
    and is misclassified into the best (``before_8pm``) tier instead of
    the worst (``after_11pm``) one.
    """

    shifted_hour = last_meal_hour if last_meal_hour >= 12.0 else last_meal_hour + 24.0
    for i, threshold in enumerate(synthetic.last_meal_tier_hours):
        if shifted_hour < threshold:
            return synthetic.last_meal_tier_labels[i]
    return synthetic.last_meal_tier_labels[-1]


def is_late_habitual_sleeper(baseline_sleep_onset_hour: float, synthetic: SyntheticAssumptions) -> bool:
    diff = circular_diff_hours(baseline_sleep_onset_hour, synthetic.late_habitual_sleeper_reference_hour)
    return diff > synthetic.late_habitual_sleeper_margin_hours


def _morning_light_effect_minutes(duration_minutes: float, source: SourceBackedAssumptions, synthetic: SyntheticAssumptions) -> float:
    no_light_delay = sum(source.morning_light_no_light_delay_minutes_range) / 2.0
    high_advance = sum(source.morning_light_high_advance_minutes_range) / 2.0
    tau = synthetic.morning_light_saturation_tau_minutes
    total_range = no_light_delay + high_advance
    return no_light_delay - total_range * (1.0 - math.exp(-duration_minutes / tau))


def _evening_screen_effect_minutes(duration_hours: float, source: SourceBackedAssumptions, synthetic: SyntheticAssumptions) -> float:
    max_delay = source.evening_screen_heavy_delay_minutes_range[1]
    tau = synthetic.evening_screen_saturation_tau_minutes
    duration_minutes = duration_hours * 60.0
    return max_delay * (1.0 - math.exp(-duration_minutes / tau))


def _last_meal_effect_minutes(last_meal_hour: float, source: SourceBackedAssumptions, synthetic: SyntheticAssumptions) -> float:
    hours_after_8pm = max(0.0, circular_diff_hours(last_meal_hour, 20.0))
    max_delay = source.late_meal_after_9pm_delay_minutes_range[1]
    tau = synthetic.meal_delay_saturation_tau_hours
    return max_delay * (1.0 - math.exp(-hours_after_8pm / tau))


def _exercise_effect_minutes(exercise_hour: float, synthetic: SyntheticAssumptions) -> float:
    if exercise_hour < synthetic.exercise_morning_cutoff_hour:
        fraction = (synthetic.exercise_morning_cutoff_hour - exercise_hour) / synthetic.exercise_morning_cutoff_hour
        return -synthetic.exercise_morning_advance_minutes_max * max(0.0, min(1.0, fraction))
    if exercise_hour > synthetic.exercise_evening_cutoff_hour:
        span = 24.0 - synthetic.exercise_evening_cutoff_hour
        fraction = (exercise_hour - synthetic.exercise_evening_cutoff_hour) / span
        return synthetic.exercise_evening_delay_minutes_max * max(0.0, min(1.0, fraction))
    return 0.0


def _caffeine_effect_minutes(caffeine_hour: float, amount_mg: float, synthetic: SyntheticAssumptions) -> float:
    if caffeine_hour <= synthetic.caffeine_late_cutoff_hour:
        return 0.0
    span = 24.0 - synthetic.caffeine_late_cutoff_hour
    fraction = min(1.0, (caffeine_hour - synthetic.caffeine_late_cutoff_hour) / span)
    dose_factor = min(1.5, amount_mg / 150.0)
    return synthetic.caffeine_late_delay_minutes_max * fraction * dose_factor


def compute_behavioral_effect(
    behavior: DailyBehaviorInputs,
    light_sensitivity: float,
    screen_sensitivity: float,
    meal_sensitivity: float,
    baseline_sleep_onset_hour: float,
    source: SourceBackedAssumptions,
    synthetic: SyntheticAssumptions,
    noise_minutes: float = 0.0,
) -> BehavioralEffect:
    """Compute one day's total behavioral DLMO shift, in minutes.

    Deterministic and pure: given the same inputs (including
    ``noise_minutes``, which the caller must supply explicitly -- this
    function never draws its own randomness), always returns the same
    result. Applies participant sensitivity multipliers, the three
    documented interaction rules, and clips the final total to the
    synthetic simulation-stability bound
    (``synthetic.daily_shift_clip_minutes``).
    """

    light_tier = morning_light_tier(behavior.morning_light_duration_minutes, synthetic)
    screen_tier = evening_screen_tier(behavior.evening_screen_duration_hours, synthetic)
    meal_tier = last_meal_tier(behavior.last_meal_hour, synthetic)

    light_effect = _morning_light_effect_minutes(behavior.morning_light_duration_minutes, source, synthetic) * light_sensitivity

    screen_effect_raw = _evening_screen_effect_minutes(behavior.evening_screen_duration_hours, source, synthetic) * screen_sensitivity
    if light_tier == "none":
        screen_effect_final = screen_effect_raw * synthetic.interaction_no_light_screen_amplifier
    elif light_tier == "moderate":
        screen_effect_final = screen_effect_raw * synthetic.interaction_moderate_light_screen_reduction
    elif light_tier == "high":
        screen_effect_final = screen_effect_raw * synthetic.interaction_high_light_screen_reduction
    else:
        screen_effect_final = screen_effect_raw

    meal_effect_raw = _last_meal_effect_minutes(behavior.last_meal_hour, source, synthetic) * meal_sensitivity
    if meal_tier == "after_11pm" and is_late_habitual_sleeper(baseline_sleep_onset_hour, synthetic):
        meal_effect_final = meal_effect_raw * synthetic.interaction_late_sleeper_late_meal_amplifier
    else:
        meal_effect_final = meal_effect_raw

    exercise_effect = _exercise_effect_minutes(behavior.exercise_hour, synthetic)
    caffeine_effect = _caffeine_effect_minutes(behavior.caffeine_hour, behavior.caffeine_amount_mg, synthetic)

    interaction_effect = (screen_effect_final - screen_effect_raw) + (meal_effect_final - meal_effect_raw)

    raw_total = light_effect + screen_effect_final + meal_effect_final + exercise_effect + caffeine_effect + noise_minutes
    total_shift = max(synthetic.daily_shift_clip_minutes[0], min(synthetic.daily_shift_clip_minutes[1], raw_total))

    return BehavioralEffect(
        light_effect=light_effect,
        screen_effect=screen_effect_final,
        meal_effect=meal_effect_final,
        exercise_effect=exercise_effect,
        caffeine_effect=caffeine_effect,
        interaction_effect=interaction_effect,
        total_shift=total_shift,
        morning_light_tier=light_tier,
        evening_screen_tier=screen_tier,
        last_meal_tier=meal_tier,
    )
