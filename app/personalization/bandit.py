"""Phase 3: a lightweight contextual bandit with Thompson sampling --
explicitly **not** generic reinforcement learning. Per-participant/
intervention-type posterior state uses the existing
``bandit_state`` table (posterior_mean, posterior_variance,
total_pulls, total_reward) unchanged.

Uses a standard Normal-Normal conjugate update (a textbook Bayesian
update, not a custom heuristic) -- transparent and auditable, matching
the brief's explicit instruction to avoid black-box optimization.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from app.personalization.config import DEFAULT_PERSONALIZATION_CONFIG, PersonalizationConfig


@dataclass(frozen=True)
class ArmPosterior:
    intervention_type: str
    posterior_mean: float
    posterior_variance: float
    total_pulls: int
    total_reward: float


@dataclass(frozen=True)
class ThompsonDraw:
    intervention_type: str
    sampled_value: float
    posterior_mean: float
    posterior_variance: float


def prior_arm(intervention_type: str, config: PersonalizationConfig = DEFAULT_PERSONALIZATION_CONFIG) -> ArmPosterior:
    return ArmPosterior(intervention_type, config.bandit_prior_mean, config.bandit_prior_variance, 0, 0.0)


def thompson_sample(arm: ArmPosterior, rng: np.random.Generator) -> ThompsonDraw:
    sampled = float(rng.normal(arm.posterior_mean, np.sqrt(max(arm.posterior_variance, 1e-9))))
    return ThompsonDraw(arm.intervention_type, sampled, arm.posterior_mean, arm.posterior_variance)


def select_action(
    arms: Sequence[ArmPosterior], rng: np.random.Generator, config: PersonalizationConfig = DEFAULT_PERSONALIZATION_CONFIG
) -> tuple:
    """Returns ``(chosen_intervention_type, all_draws)``.

    **Exploration safeguard**: a clearly dominant arm (posterior mean
    ahead of every other arm by more than ``exploration_dominance_margin``)
    is never displaced by a single lucky sample from a long-shot arm --
    the system does not "sacrifice a user's clearly superior
    intervention merely for arbitrary exploration." Otherwise, the
    highest-sampled arm wins (ordinary Thompson sampling)."""

    if not arms:
        raise ValueError("select_action requires at least one candidate arm")

    draws = [thompson_sample(arm, rng) for arm in arms]
    best_by_mean = max(draws, key=lambda d: d.posterior_mean)
    best_by_sample = max(draws, key=lambda d: d.sampled_value)

    if best_by_sample is not best_by_mean:
        dominance = best_by_mean.posterior_mean - best_by_sample.posterior_mean
        if dominance > config.exploration_dominance_margin:
            return best_by_mean.intervention_type, draws

    return best_by_sample.intervention_type, draws


def update_posterior(
    arm: ArmPosterior, reward: float, config: PersonalizationConfig = DEFAULT_PERSONALIZATION_CONFIG
) -> ArmPosterior:
    """One Normal-Normal conjugate Bayesian update from a single new
    reward observation, with a fixed assumed observation-noise
    variance (``bandit_reward_observation_variance``) -- a documented
    project default, not a fitted noise model."""

    obs_variance = config.bandit_reward_observation_variance
    new_variance = 1.0 / (1.0 / arm.posterior_variance + 1.0 / obs_variance)
    new_mean = new_variance * (arm.posterior_mean / arm.posterior_variance + reward / obs_variance)

    return ArmPosterior(
        intervention_type=arm.intervention_type,
        posterior_mean=new_mean,
        posterior_variance=new_variance,
        total_pulls=arm.total_pulls + 1,
        total_reward=arm.total_reward + reward,
    )
