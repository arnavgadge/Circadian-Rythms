"""Configuration for the Phase 13 long-term personalization system.

Every threshold here is a **project engineering graduation rule**, not
a claim of statistical or clinical significance -- see
``docs/personalization_engine.md`` "Evidence thresholds".
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PersonalizationConfig:
    personalization_config_version: str = "1.0.0"

    # --- Phase 1: personal ranking activation ---
    ranking_min_observations: int = 3
    ranking_min_weeks_active: int = 3

    # --- Phase 2: personal effect model activation ---
    effect_model_min_observations: int = 14
    effect_model_min_weeks_active: int = 6

    # --- Phase 3: adaptive (bandit) policy activation ---
    adaptive_min_observations: int = 42
    adaptive_min_weeks_active: int = 12  # ~3 months

    # --- Evidence-strength labels (engineering metadata, not p-values) ---
    evidence_insufficient_max: int = 2       # < 3
    evidence_weak_max: int = 6               # 3-6
    evidence_emerging_max: int = 13          # 7-13
    evidence_moderate_max: int = 20          # 14-20
    # 21+ -> "stronger"

    # --- Literature/personal blending ---
    # During the early PERSONAL_RANKING/blended window, personal
    # evidence is blended with the literature value rather than
    # abruptly replacing it.
    blended_personal_weight: float = 0.40
    blended_literature_weight: float = 0.60
    # Above this many observations (with a valid model), the personal
    # estimate is used at 100% -- provided validity checks pass.
    full_personal_min_observations: int = 21

    # --- Model validity checks (Phase 2 effect model) ---
    max_plausible_effect_minutes: float = 120.0  # a coefficient beyond this is treated as degenerate/unstable
    min_r_squared_for_validity: float = 0.05
    max_confidence_interval_width_minutes: float = 200.0
    min_compliance_variation: float = 0.05  # stddev of compliance_degree across observations

    # --- Graduated-target aggressiveness adjustment ---
    # Personalization may nudge Phase 10's ~50% graduated-target
    # fraction once real evidence exists -- bounded, never removing
    # Phase 10's own feasibility/bounds constraints.
    max_target_aggressiveness_adjustment: float = 0.15

    # --- Bandit (Thompson sampling) ---
    bandit_reward_observation_variance: float = 25.0  # assumed noise variance of one reward observation
    bandit_prior_mean: float = 0.0
    bandit_prior_variance: float = 100.0
    # Exploration safeguard: an arm is never sampled-selected over a
    # clearly superior arm whose posterior mean exceeds it by more
    # than this margin with high confidence (see app.personalization.bandit).
    exploration_dominance_margin: float = 20.0

    # --- Refresh policy ---
    # A personal-effect/model refresh is only triggered when at least
    # this many *new* compliance observations have accumulated since
    # the stored model's own observation count -- avoids creating an
    # unbounded number of near-identical model updates.
    min_new_observations_for_refresh: int = 1


DEFAULT_PERSONALIZATION_CONFIG = PersonalizationConfig()
