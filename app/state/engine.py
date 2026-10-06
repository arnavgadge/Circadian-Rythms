"""The authoritative three-layer circadian state transition.

This is the **only** place the ``intrinsic -> adapted -> current``
transition is implemented. Phase 3's synthetic generator and any
future production inference both call into this module; neither
maintains its own copy of the equations (see
``app.synthetic.dlmo_state`` for the thin backward-compatible
translation layer Phase 3 now uses).

**Temporal ordering** (see :func:`step`): within one call, the adapted
state is computed first, then the current state -- but current's
pull-toward-adapted term deliberately uses the *previous* day's adapted
value, not the one just computed in the same call. This is not an
oversight: pulling current toward an adapted value that only becomes
known partway through today's own update would be a same-day circular
dependency with no clear meaning ("pull toward where you're about to
move to today"). Current is pulled toward the equilibrium that existed
coming into today. Both Phase 3 and this engine use this same
convention; changing it would change Phase 3's historical trajectories.

**Determinism**: :func:`step` takes an explicit ``noise_minutes`` /
``state_noise_hours`` value (default ``0.0``) rather than drawing its
own randomness -- it is fully deterministic unless a caller explicitly
supplies nonzero noise. :func:`step_stochastic` is the only function in
this module that draws randomness (from a caller-supplied
``numpy.random.Generator``), and it does so visibly, by calling
:func:`step` with explicit noise values -- there is no hidden RNG
inside the deterministic path.
"""

from __future__ import annotations

import math
from datetime import date as date_cls
from typing import Optional

import numpy as np

from app.state.behavioral_effect import BehavioralEffect, DailyBehaviorInputs, compute_behavioral_effect
from app.state.circadian_state import CircadianState, ParticipantPhaseTraits, StateTransitionDebug
from app.state.config import DEFAULT_STATE_ENGINE_CONFIG, StateEngineConfig
from app.synthetic.config import (
    DEFAULT_SOURCE_BACKED,
    DEFAULT_SYNTHETIC,
    SourceBackedAssumptions,
    SyntheticAssumptions,
)
from app.synthetic.time_utils import circular_diff_hours, normalize_hour


def _clip_to_bound(hour: float, anchor_hour: float, bound_hours: float) -> float:
    diff = circular_diff_hours(hour, anchor_hour)
    if diff > bound_hours:
        return normalize_hour(anchor_hour + bound_hours)
    if diff < -bound_hours:
        return normalize_hour(anchor_hour - bound_hours)
    return hour


def initialize_state(
    intrinsic_dlmo_hour: float,
    chronotype: Optional[str] = None,
    config: StateEngineConfig = DEFAULT_STATE_ENGINE_CONFIG,
    date: Optional[date_cls] = None,
) -> CircadianState:
    """Deterministically initialize a coherent starting state.

    ``adapted_DLMO = intrinsic_DLMO + config.initialization_offset_hours``
    (zero by default); ``current_DLMO = adapted_DLMO``. Current is never
    initialized far from intrinsic -- both start at the same small,
    configurable offset.
    """

    adapted_hour = normalize_hour(intrinsic_dlmo_hour + config.initialization_offset_hours)
    return CircadianState(
        intrinsic_dlmo_hour=normalize_hour(intrinsic_dlmo_hour),
        adapted_dlmo_hour=adapted_hour,
        current_dlmo_hour=adapted_hour,
        chronotype=chronotype,
        date=date,
    )


def initialize_state_stochastic(
    intrinsic_dlmo_hour: float,
    rng: np.random.Generator,
    chronotype: Optional[str] = None,
    config: StateEngineConfig = DEFAULT_STATE_ENGINE_CONFIG,
    date: Optional[date_cls] = None,
) -> CircadianState:
    """Explicit stochastic counterpart to :func:`initialize_state`.

    Adds a small independent random nudge (``Normal(0,
    config.initialization_offset_sd_hours)``) to each of adapted/current
    at onboarding, matching Phase 3's population-generation behavior.
    Never called by the deterministic inference path -- callers that
    want simulation-time variability must call this explicitly.
    """

    intrinsic = normalize_hour(intrinsic_dlmo_hour)
    adapted_hour = normalize_hour(
        intrinsic + config.initialization_offset_hours + float(rng.normal(0.0, config.initialization_offset_sd_hours))
    )
    current_hour = normalize_hour(adapted_hour + float(rng.normal(0.0, config.initialization_offset_sd_hours)))
    return CircadianState(
        intrinsic_dlmo_hour=intrinsic,
        adapted_dlmo_hour=adapted_hour,
        current_dlmo_hour=current_hour,
        chronotype=chronotype,
        date=date,
    )


def step(
    previous_state: CircadianState,
    behavior: DailyBehaviorInputs,
    traits: ParticipantPhaseTraits,
    config: StateEngineConfig = DEFAULT_STATE_ENGINE_CONFIG,
    source: SourceBackedAssumptions = DEFAULT_SOURCE_BACKED,
    synthetic: SyntheticAssumptions = DEFAULT_SYNTHETIC,
    noise_minutes: float = 0.0,
    state_noise_hours: float = 0.0,
    apply_continuity_cap: bool = True,
    date: Optional[date_cls] = None,
) -> tuple:
    """Advance the circadian state by exactly one day. Deterministic.

    Returns ``(new_state, debug)``. ``noise_minutes`` feeds into the
    behavioral-effect clip (mirrors Phase 3's simulation-time noise
    term); ``state_noise_hours`` is added directly to the current-DLMO
    update (mirrors Phase 3's separate state-noise term). Both default
    to ``0.0`` -- pass nonzero values only from an explicitly stochastic
    caller (see :func:`step_stochastic`).

    ``apply_continuity_cap`` gates the Phase-6-introduced final safety
    clamp on the total day-over-day current-DLMO change (see
    ``StateEngineConfig.daily_continuity_cap_minutes``). It defaults to
    ``True`` for ordinary use, but Phase 3's replay-compatibility layer
    passes ``False`` so historical trajectories -- generated before
    this cap existed -- reproduce exactly.
    """

    effect = compute_behavioral_effect(
        behavior=behavior,
        light_sensitivity=traits.light_sensitivity,
        screen_sensitivity=traits.screen_sensitivity,
        meal_sensitivity=traits.meal_sensitivity,
        baseline_sleep_onset_hour=traits.baseline_sleep_onset_hour,
        source=source,
        synthetic=synthetic,
        noise_minutes=noise_minutes,
    )
    delta_hours = effect.total_shift / 60.0

    # --- Adapted DLMO: updated first ---
    behavioral_equilibrium_hour = normalize_hour(previous_state.adapted_dlmo_hour + delta_hours)
    adapted_pull = config.adaptation_rate * circular_diff_hours(
        behavioral_equilibrium_hour, previous_state.adapted_dlmo_hour
    )
    intrinsic_pull = config.intrinsic_recovery_rate * circular_diff_hours(
        previous_state.intrinsic_dlmo_hour, previous_state.adapted_dlmo_hour
    )
    raw_adapted_delta = adapted_pull + intrinsic_pull
    new_adapted_hour = normalize_hour(previous_state.adapted_dlmo_hour + raw_adapted_delta)
    new_adapted_hour = _clip_to_bound(new_adapted_hour, previous_state.intrinsic_dlmo_hour, config.adapted_max_offset_hours)

    # --- Current DLMO: pulled toward the PREVIOUS day's adapted value ---
    current_pull_hours = config.current_pull_rate * circular_diff_hours(
        previous_state.adapted_dlmo_hour, previous_state.current_dlmo_hour
    )
    unclamped_current_delta = delta_hours + current_pull_hours + state_noise_hours
    new_current_hour = normalize_hour(previous_state.current_dlmo_hour + unclamped_current_delta)

    continuity_cap_applied = False
    if apply_continuity_cap and config.daily_continuity_cap_minutes is not None:
        cap_hours = config.daily_continuity_cap_minutes / 60.0
        actual_change = circular_diff_hours(new_current_hour, previous_state.current_dlmo_hour)
        if abs(actual_change) > cap_hours:
            capped_change = math.copysign(cap_hours, actual_change)
            new_current_hour = normalize_hour(previous_state.current_dlmo_hour + capped_change)
            continuity_cap_applied = True

    new_current_hour = _clip_to_bound(new_current_hour, previous_state.intrinsic_dlmo_hour, config.current_max_offset_hours)

    new_state = CircadianState(
        intrinsic_dlmo_hour=previous_state.intrinsic_dlmo_hour,
        adapted_dlmo_hour=new_adapted_hour,
        current_dlmo_hour=new_current_hour,
        chronotype=previous_state.chronotype or traits.chronotype,
        date=date,
    )
    debug = StateTransitionDebug(
        behavioral_effect=effect,
        behavioral_equilibrium_hour=behavioral_equilibrium_hour,
        raw_adapted_delta_hours=raw_adapted_delta,
        raw_current_delta_hours=delta_hours,
        current_pull_to_adapted_hours=current_pull_hours,
        current_state_noise_hours=state_noise_hours,
        unclamped_current_delta_hours=unclamped_current_delta,
        continuity_cap_applied=continuity_cap_applied,
    )
    return new_state, debug


def step_stochastic(
    previous_state: CircadianState,
    behavior: DailyBehaviorInputs,
    traits: ParticipantPhaseTraits,
    rng: np.random.Generator,
    config: StateEngineConfig = DEFAULT_STATE_ENGINE_CONFIG,
    source: SourceBackedAssumptions = DEFAULT_SOURCE_BACKED,
    synthetic: SyntheticAssumptions = DEFAULT_SYNTHETIC,
    apply_continuity_cap: bool = True,
    date: Optional[date_cls] = None,
) -> tuple:
    """Explicit stochastic counterpart to :func:`step`.

    Draws the day-level behavioral noise (``Normal(0,
    synthetic.day_level_noise_sd_minutes)``) and the state noise
    (``Normal(0, config.daily_state_noise_sd_minutes)``) from ``rng``,
    then delegates to :func:`step` with those explicit values -- the
    only randomness anywhere in this module is drawn here, visibly, by
    a function whose name says so.
    """

    noise_minutes = float(rng.normal(0.0, synthetic.day_level_noise_sd_minutes))
    state_noise_hours = float(rng.normal(0.0, config.daily_state_noise_sd_minutes / 60.0))
    return step(
        previous_state=previous_state,
        behavior=behavior,
        traits=traits,
        config=config,
        source=source,
        synthetic=synthetic,
        noise_minutes=noise_minutes,
        state_noise_hours=state_noise_hours,
        apply_continuity_cap=apply_continuity_cap,
        date=date,
    )
