"""Recent phase-shift effect per contributor signal.

Reuses the exact same authoritative behavioral-effect model Phase 6
uses (``app.state.behavioral_effect.compute_behavioral_effect``) --
this module does not define a second, potentially-contradictory
effect calculation. For each of the six window days, the shared model
is called once (with ``noise_minutes=0.0``, since contributor ranking
must be deterministic -- see ``docs/contributor_ranking.md``
"Determinism"), and the four relevant per-signal components (light,
screen, meal, exercise) are read off its breakdown and averaged across
the days that have data.

Caffeine is not a ranked contributor signal (see the locked five-signal
list), but ``compute_behavioral_effect`` requires a caffeine input to
run at all; a neutral placeholder (10:00, 0 mg -- inside the
"no effect" zone of the caffeine curve) is supplied so caffeine never
contributes a fabricated effect to the other four signals' results.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

from app.state.behavioral_effect import DailyBehaviorInputs, compute_behavioral_effect
from app.state.circadian_state import ParticipantPhaseTraits
from app.synthetic.config import DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC

_NEUTRAL_CAFFEINE_HOUR = 10.0  # inside the caffeine model's no-effect window
_NEUTRAL_CAFFEINE_AMOUNT_MG = 0.0


def _is_missing(value) -> bool:
    """True for ``None`` or NaN -- window values may be sourced from a
    database (``NULL`` -> ``None``) or a pandas DataFrame (missing ->
    ``float('nan')``); both must count as missing here."""

    return value is None or (isinstance(value, float) and math.isnan(value))


@dataclass(frozen=True)
class SignalEffect:
    signal: str
    mean_signed_effect_minutes: Optional[float]
    days_used: int
    days_available: int


def _mean_of_present(values: Sequence) -> Optional[float]:
    present = [v for v in values if not _is_missing(v)]
    if not present:
        return None
    return sum(present) / len(present)


def compute_window_phase_effects(
    traits: ParticipantPhaseTraits,
    window_morning_light_duration_minutes: Sequence,
    window_evening_screen_duration_hours: Sequence,
    window_last_meal_hours: Sequence,
    window_exercise_hours: Sequence,
) -> dict:
    """Compute the mean recent signed phase effect (minutes) for the four
    effect-bearing signals (morning_light, evening_screen, meal_timing,
    exercise). Returns a dict keyed by signal name -> :class:`SignalEffect`.

    A day is skipped (not zero-filled) whenever any of its four required
    raw values is missing -- an incomplete day contributes no fabricated
    effect rather than a misleadingly confident partial one.
    """

    n_days = max(
        len(window_morning_light_duration_minutes),
        len(window_evening_screen_duration_hours),
        len(window_last_meal_hours),
        len(window_exercise_hours),
    )

    light_effects, screen_effects, meal_effects, exercise_effects = [], [], [], []
    days_with_data = 0

    for i in range(n_days):
        light = window_morning_light_duration_minutes[i] if i < len(window_morning_light_duration_minutes) else None
        screen = window_evening_screen_duration_hours[i] if i < len(window_evening_screen_duration_hours) else None
        meal = window_last_meal_hours[i] if i < len(window_last_meal_hours) else None
        exercise = window_exercise_hours[i] if i < len(window_exercise_hours) else None

        if any(_is_missing(v) for v in (light, screen, meal, exercise)):
            continue

        days_with_data += 1
        behavior = DailyBehaviorInputs(
            morning_light_duration_minutes=light,
            evening_screen_duration_hours=screen,
            last_meal_hour=meal,
            exercise_hour=exercise,
            caffeine_hour=_NEUTRAL_CAFFEINE_HOUR,
            caffeine_amount_mg=_NEUTRAL_CAFFEINE_AMOUNT_MG,
        )
        effect = compute_behavioral_effect(
            behavior=behavior,
            light_sensitivity=traits.light_sensitivity,
            screen_sensitivity=traits.screen_sensitivity,
            meal_sensitivity=traits.meal_sensitivity,
            baseline_sleep_onset_hour=traits.baseline_sleep_onset_hour,
            source=DEFAULT_SOURCE_BACKED,
            synthetic=DEFAULT_SYNTHETIC,
            noise_minutes=0.0,
        )
        light_effects.append(effect.light_effect)
        screen_effects.append(effect.screen_effect)
        meal_effects.append(effect.meal_effect)
        exercise_effects.append(effect.exercise_effect)

    return {
        "morning_light": SignalEffect("morning_light", _mean_of_present(light_effects), days_with_data, n_days),
        "evening_screen": SignalEffect("evening_screen", _mean_of_present(screen_effects), days_with_data, n_days),
        "meal_timing": SignalEffect("meal_timing", _mean_of_present(meal_effects), days_with_data, n_days),
        "exercise": SignalEffect("exercise", _mean_of_present(exercise_effects), days_with_data, n_days),
    }
