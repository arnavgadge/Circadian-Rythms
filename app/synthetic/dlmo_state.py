"""Backward-compatible translation layer over the Phase 6 state engine.

Phase 3 originally implemented the three-layer state transition and
the behavioral-effect model directly in this module. Phase 6 promoted
both to ``app.state`` as the single authoritative implementation
shared by simulation and future production inference (see
``app.state.engine`` and ``app.state.behavioral_effect``) -- per the
Phase 6 requirement that there must never be two copies of the same
equations that could silently disagree.

This module now does nothing but translate between Phase 3's original
types (``DailyBehaviorRecord``, ``ParticipantTraits``, ``DLMOState``,
``DailyEffectBreakdown``) and the engine's own types
(``DailyBehaviorInputs``, ``ParticipantPhaseTraits``, ``CircadianState``,
``BehavioralEffect``), so ``app.synthetic.simulator`` and every
existing Phase 3 test keep working unchanged. The random-number-draw
order is preserved exactly (behavioral noise, then state noise) so
seeded Phase 3 runs reproduce bit-for-bit.

The Phase-6-introduced final continuity cap
(``StateEngineConfig.daily_continuity_cap_minutes``) is explicitly
**disabled** here (``apply_continuity_cap=False``), since it did not
exist when the historical Phase 3 synthetic dataset was generated --
enabling it now would silently change already-generated trajectories
on the rare day where it would bind. See ``docs/state_engine.md``
"Relationship to Phase 3" for the full rationale, and
``app.state.replay`` for the consistency check this guarantees.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.state.behavioral_effect import (
    DailyBehaviorInputs,
    classify_tier,
    compute_behavioral_effect,
    evening_screen_tier,
    is_late_habitual_sleeper,
    last_meal_tier,
    morning_light_tier,
)
from app.state.circadian_state import CircadianState, ParticipantPhaseTraits
from app.state.config import StateEngineConfig
from app.state.engine import step as engine_step
from app.synthetic.behavior import DailyBehaviorRecord
from app.synthetic.config import SourceBackedAssumptions, SyntheticAssumptions
from app.synthetic.population import ParticipantTraits

__all__ = [
    "DLMOState",
    "DailyEffectBreakdown",
    "classify_tier",
    "morning_light_tier",
    "evening_screen_tier",
    "last_meal_tier",
    "compute_daily_effect",
    "step",
]


def _phase3_state_config(synthetic: SyntheticAssumptions) -> StateEngineConfig:
    """Build a :class:`StateEngineConfig` whose three-layer parameters
    match ``synthetic`` exactly, for bit-for-bit Phase 3 compatibility."""

    return StateEngineConfig(
        adaptation_rate=synthetic.adapted_daily_pull_to_behavior_fraction,
        intrinsic_recovery_rate=synthetic.adapted_daily_pull_to_intrinsic_fraction,
        adapted_max_offset_hours=synthetic.adapted_bound_hours_from_intrinsic,
        current_pull_rate=synthetic.current_daily_pull_to_adapted_fraction,
        current_max_offset_hours=synthetic.current_bound_hours_from_intrinsic,
        daily_continuity_cap_minutes=None,  # disabled: see module docstring
        daily_state_noise_sd_minutes=synthetic.daily_state_noise_sd_minutes,
    )


@dataclass(frozen=True)
class DLMOState:
    """Backward-compatible view over :class:`app.state.circadian_state.CircadianState`.

    Field names (``intrinsic_hour``/``adapted_hour``/``current_hour``)
    match Phase 3's original short names exactly; the canonical Phase 6
    engine uses the more explicit ``*_dlmo_hour`` names internally (see
    :func:`_to_circadian_state`/:func:`_from_circadian_state`).
    """

    intrinsic_hour: float
    adapted_hour: float
    current_hour: float


def _to_circadian_state(state: DLMOState) -> CircadianState:
    return CircadianState(
        intrinsic_dlmo_hour=state.intrinsic_hour,
        adapted_dlmo_hour=state.adapted_hour,
        current_dlmo_hour=state.current_hour,
    )


def _from_circadian_state(state: CircadianState) -> DLMOState:
    return DLMOState(
        intrinsic_hour=state.intrinsic_dlmo_hour,
        adapted_hour=state.adapted_dlmo_hour,
        current_hour=state.current_dlmo_hour,
    )


class DailyEffectBreakdown:
    """Backward-compatible view over :class:`app.state.behavioral_effect.BehavioralEffect`.

    Field names match Phase 3's original ``DailyEffectBreakdown``
    exactly (``light_effect_minutes``, ``clipped_total_minutes``, ...).
    """

    def __init__(self, behavioral_effect, raw_total_minutes: float, noise_minutes: float) -> None:
        self._effect = behavioral_effect
        self.light_effect_minutes = behavioral_effect.light_effect
        self.screen_effect_minutes = behavioral_effect.screen_effect
        self.meal_effect_minutes = behavioral_effect.meal_effect
        self.exercise_effect_minutes = behavioral_effect.exercise_effect
        self.caffeine_effect_minutes = behavioral_effect.caffeine_effect
        self.noise_minutes = noise_minutes
        self.raw_total_minutes = raw_total_minutes
        self.clipped_total_minutes = behavioral_effect.total_shift
        self.morning_light_tier = behavioral_effect.morning_light_tier
        self.evening_screen_tier = behavioral_effect.evening_screen_tier
        self.last_meal_tier = behavioral_effect.last_meal_tier


def compute_daily_effect(
    behavior: DailyBehaviorRecord,
    participant: ParticipantTraits,
    source: SourceBackedAssumptions,
    synthetic: SyntheticAssumptions,
    state_rng: np.random.Generator,
) -> DailyEffectBreakdown:
    """Compute one day's total behavioral DLMO shift, in minutes.

    Draws the behavioral noise term from ``state_rng`` first (matching
    Phase 3's original draw order), then delegates the actual
    computation to :func:`app.state.behavioral_effect.compute_behavioral_effect`.
    """

    noise = float(state_rng.normal(0.0, synthetic.day_level_noise_sd_minutes))

    behavior_inputs = DailyBehaviorInputs(
        morning_light_duration_minutes=behavior.morning_light_duration_minutes,
        evening_screen_duration_hours=behavior.evening_screen_duration_hours,
        last_meal_hour=behavior.last_meal_hour,
        exercise_hour=behavior.exercise_hour,
        caffeine_hour=behavior.caffeine_hour,
        caffeine_amount_mg=behavior.caffeine_amount_mg,
    )
    effect = compute_behavioral_effect(
        behavior=behavior_inputs,
        light_sensitivity=participant.light_sensitivity,
        screen_sensitivity=participant.screen_sensitivity,
        meal_sensitivity=participant.meal_sensitivity,
        baseline_sleep_onset_hour=participant.baseline_sleep_onset_hour,
        source=source,
        synthetic=synthetic,
        noise_minutes=noise,
    )
    raw_total = effect.light_effect + effect.screen_effect + effect.meal_effect + effect.exercise_effect + effect.caffeine_effect + noise
    return DailyEffectBreakdown(effect, raw_total_minutes=raw_total, noise_minutes=noise)


def step(
    previous_state: DLMOState,
    behavior: DailyBehaviorRecord,
    participant: ParticipantTraits,
    source: SourceBackedAssumptions,
    synthetic: SyntheticAssumptions,
    state_rng: np.random.Generator,
) -> tuple:
    """Advance the DLMO state by exactly one day (Phase 3 compatibility wrapper).

    Delegates to :func:`app.state.engine.step` with the Phase-6
    continuity cap disabled, preserving Phase 3's exact historical
    behavior. See the module docstring for the full rationale.
    """

    noise = float(state_rng.normal(0.0, synthetic.day_level_noise_sd_minutes))
    state_noise_hours = float(state_rng.normal(0.0, synthetic.daily_state_noise_sd_minutes / 60.0))

    behavior_inputs = DailyBehaviorInputs(
        morning_light_duration_minutes=behavior.morning_light_duration_minutes,
        evening_screen_duration_hours=behavior.evening_screen_duration_hours,
        last_meal_hour=behavior.last_meal_hour,
        exercise_hour=behavior.exercise_hour,
        caffeine_hour=behavior.caffeine_hour,
        caffeine_amount_mg=behavior.caffeine_amount_mg,
    )
    traits = ParticipantPhaseTraits(
        intrinsic_dlmo_hour=participant.intrinsic_dlmo_hour,
        baseline_sleep_onset_hour=participant.baseline_sleep_onset_hour,
        light_sensitivity=participant.light_sensitivity,
        screen_sensitivity=participant.screen_sensitivity,
        meal_sensitivity=participant.meal_sensitivity,
    )
    config = _phase3_state_config(synthetic)

    new_circadian_state, debug = engine_step(
        previous_state=_to_circadian_state(previous_state),
        behavior=behavior_inputs,
        traits=traits,
        config=config,
        source=source,
        synthetic=synthetic,
        noise_minutes=noise,
        state_noise_hours=state_noise_hours,
        apply_continuity_cap=False,
    )
    new_state = _from_circadian_state(new_circadian_state)

    raw_total = (
        debug.behavioral_effect.light_effect
        + debug.behavioral_effect.screen_effect
        + debug.behavioral_effect.meal_effect
        + debug.behavioral_effect.exercise_effect
        + debug.behavioral_effect.caffeine_effect
        + noise
    )
    effect_breakdown = DailyEffectBreakdown(debug.behavioral_effect, raw_total_minutes=raw_total, noise_minutes=noise)
    return new_state, effect_breakdown
