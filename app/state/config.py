"""Configuration for the CircadianIQ state engine.

Every numeric parameter governing the three-layer state transition
(``intrinsic -> adapted -> current``) lives here. These are the
project's **synthetic modeling framework**, not validated human
physiology -- see ``docs/state_engine.md`` "Synthetic-assumption
disclaimer" for the full discussion. The default values match, by
construction, the equivalent parameters already used (under different
names) by the Phase 3 synthetic generator -- see
``app.synthetic.config.SyntheticAssumptions`` -- so that this engine
reproduces Phase 3's historical trajectories exactly (see
``app.state.replay`` and ``docs/state_engine.md`` "Relationship to
Phase 3").

The behavioral-effect curve anchors (morning light / evening screen /
last meal / exercise / caffeine) and the source-backed vs. synthetic
citation labeling are **not** duplicated here: they are imported
directly from ``app.synthetic.config`` (see
``app.state.behavioral_effect``), so there is exactly one place that
claims a number is source-backed and exactly one place that computes
each effect curve.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StateEngineConfig:
    """Three-layer state transition parameters.

    Field names here are the Phase 6 canonical names; each has an exact
    Phase 3 equivalent (noted per-field) that this replaces as the
    single authoritative source of these numbers.
    """

    state_config_version: str = "1.0.0"

    # --- Adapted DLMO ---
    # ~1%/day toward the behavioral equilibrium.
    # (Phase 3: SyntheticAssumptions.adapted_daily_pull_to_behavior_fraction)
    adaptation_rate: float = 0.01
    # ~0.5%/day back toward intrinsic DLMO.
    # (Phase 3: SyntheticAssumptions.adapted_daily_pull_to_intrinsic_fraction)
    intrinsic_recovery_rate: float = 0.005
    # Adapted DLMO stays within this many hours of intrinsic DLMO.
    # (Phase 3: SyntheticAssumptions.adapted_bound_hours_from_intrinsic)
    adapted_max_offset_hours: float = 2.0

    # --- Current DLMO ---
    # Fraction of the (adapted - current) gap closed per day.
    # (Phase 3: SyntheticAssumptions.current_daily_pull_to_adapted_fraction)
    current_pull_rate: float = 0.5
    # Current DLMO stays within this many hours of intrinsic DLMO.
    # (Phase 3: SyntheticAssumptions.current_bound_hours_from_intrinsic)
    current_max_offset_hours: float = 3.0

    # --- Continuity safety net (new in Phase 6) ---
    # A final cap on the total day-over-day change in current_DLMO --
    # catches numerical bugs, incorrect circular arithmetic, or extreme
    # synthetic input producing an implausible jump. This is distinct
    # from (and applied *after*) the behavioral-effect clip already
    # present in the Phase 3 effect model (see
    # ``app.state.behavioral_effect``): that clip bounds one day's raw
    # behavioral push; this bounds the *total* resulting state change,
    # including the pull-toward-adapted term and any noise.
    #
    # This is disabled (``None``) when replaying Phase 3 trajectories,
    # so historical synthetic data -- generated before this cap
    # existed -- replays bit-for-bit; it is enabled by default for new
    # (Phase 6+) state-engine use. See ``app.state.replay`` and
    # ``docs/state_engine.md`` "Limitations".
    daily_continuity_cap_minutes: float = 60.0

    # --- Initialization ---
    # At onboarding, adapted/current DLMO start this many hours away
    # from intrinsic DLMO (both start at the SAME small offset, so the
    # state begins coherent -- current is never initialized far from
    # intrinsic). Zero by default (deterministic); Phase 3's population
    # generator instead draws a small per-participant random nudge --
    # see ``app.state.engine.initialize_state_stochastic``.
    initialization_offset_hours: float = 0.0
    # Standard deviation used only by the explicit stochastic
    # initializer (never by the deterministic one).
    initialization_offset_sd_hours: float = 0.10

    # --- Daily state noise (simulation-time only) ---
    # Standard deviation of the small Gaussian noise added to the
    # current-DLMO update in *stochastic* simulation mode. Never used by
    # the deterministic inference path (see "DAILY NOISE" in the brief
    # and ``docs/state_engine.md`` "Circular-time handling").
    # (Phase 3: SyntheticAssumptions.daily_state_noise_sd_minutes)
    daily_state_noise_sd_minutes: float = 5.0


DEFAULT_STATE_ENGINE_CONFIG = StateEngineConfig()
