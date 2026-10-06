"""AUDIT 15 -- Bandit safety, in a controlled simulated environment.

Exercises ``app.personalization.bandit`` directly (never
``app/models/`` held-out ML test data) to check: uncertainty is part
of the policy's internal state; exploration is structurally bounded;
the action space can never escape the caller-supplied (safety-approved)
arm set; and, over a long stationary-reward simulation, the policy's
selected-arm reward improves directionally over time.

It also pins down (regression-tests) a real architectural finding: the
bandit module is not currently wired into the production recommendation
path at all -- ``ADAPTIVE_POLICY`` behaves identically to ``LITERATURE``
today (this matches ``docs/personalization_engine.md`` /
``docs/recommendation_engine.md`` section 12's explicit disclosure, so
it is reported as a documented scope gap, not fixed here).
"""

from __future__ import annotations

import numpy as np
import pytest

from app.personalization.bandit import ArmPosterior, prior_arm, select_action, update_posterior
from app.personalization.config import DEFAULT_PERSONALIZATION_CONFIG
from app.safety.config import DEFAULT_SAFETY_CONFIG
from app.database.seed import _REFERENCE_RECOMMENDATIONS


def test_bandit_arm_universe_is_a_subset_of_the_approved_safety_catalogue():
    """The bandit's action space (intervention_type) must never be able
    to select something outside the safety-approved set -- verified at
    the type level by checking every catalogue intervention_type
    (the only legitimate source of bandit arms) is itself a member of
    app.safety.config.DEFAULT_SAFETY_CONFIG.approved_intervention_types."""

    catalogue_types = {entry["intervention_type"] for entry in _REFERENCE_RECOMMENDATIONS}
    approved = set(DEFAULT_SAFETY_CONFIG.approved_intervention_types)
    assert catalogue_types <= approved, catalogue_types - approved


def test_select_action_never_returns_an_arm_outside_the_input_set():
    """Structural safety: select_action can only ever return one of the
    intervention_types it was handed -- it has no path to invent a new
    action, regardless of RNG seed."""

    rng = np.random.default_rng(7)
    arms = [
        ArmPosterior("screen", 5.0, 10.0, 3, 15.0),
        ArmPosterior("light", 2.0, 50.0, 1, 2.0),
        ArmPosterior("meal", -3.0, 5.0, 10, -30.0),
    ]
    allowed = {a.intervention_type for a in arms}
    for _ in range(200):
        chosen, draws = select_action(arms, rng, DEFAULT_PERSONALIZATION_CONFIG)
        assert chosen in allowed
        assert {d.intervention_type for d in draws} <= allowed


def test_posterior_variance_is_present_and_shrinks_monotonically_with_evidence():
    """Uncertainty is explicit state on the arm (posterior_variance),
    and strictly shrinks with each new observation (standard conjugate
    Normal-Normal behavior) -- never flat or growing from more data."""

    arm = prior_arm("screen")
    variances = [arm.posterior_variance]
    rng = np.random.default_rng(3)
    for _ in range(10):
        arm = update_posterior(arm, reward=float(rng.normal(5.0, 2.0)))
        variances.append(arm.posterior_variance)

    for earlier, later in zip(variances, variances[1:]):
        assert later < earlier


def test_bandit_average_reward_improves_over_multiweek_stationary_simulation():
    """Controlled simulated environment: three arms with fixed
    (stationary) true means, run for ~9 "weeks" (300 pulls, one per
    simulated day-ish decision point -- matches the diagnostics
    script's own harness). The average reward of the arm actually
    CHOSEN each round should trend up over the run: it does not need
    to reach optimality, but a flat/declining trend with a stationary
    environment would indicate the policy is not learning at all."""

    rng = np.random.default_rng(42)
    config = DEFAULT_PERSONALIZATION_CONFIG
    true_means = {"screen": 4.0, "light": 18.0, "meal": -2.0}
    true_noise_sd = 5.0

    arms = {name: prior_arm(name, config) for name in true_means}
    chosen_rewards = []

    n_rounds = 300
    for _ in range(n_rounds):
        chosen, _ = select_action(list(arms.values()), rng, config)
        reward = float(rng.normal(true_means[chosen], true_noise_sd))
        arms[chosen] = update_posterior(arms[chosen], reward, config)
        chosen_rewards.append(reward)

    first_block = chosen_rewards[:50]
    last_block = chosen_rewards[-50:]
    assert sum(last_block) / len(last_block) > sum(first_block) / len(first_block), (
        "average selected-arm reward did not improve over a long stationary-reward "
        "simulation -- the policy does not appear to be learning"
    )


def test_adaptive_policy_phase_is_not_actually_wired_to_the_bandit_in_production():
    """Documented architectural finding (not a bug): app.personalization
    .dispatcher.personalize_recommendations never calls
    app.personalization.bandit.select_action anywhere, and
    app.personalization.db_adapter has a read path (load_bandit_state)
    but no write/persistence path for BanditState at all. This test
    pins that current, documented state down so a future change that
    silently wires (or silently breaks) it is caught either way."""

    import app.personalization.dispatcher as dispatcher_module
    import app.personalization.db_adapter as db_adapter_module

    source = open(dispatcher_module.__file__, encoding="utf-8").read()
    assert "select_action" not in source and "bandit" not in source.lower()

    db_adapter_source = open(db_adapter_module.__file__, encoding="utf-8").read()
    assert "def load_bandit_state" in db_adapter_source
    assert "def save_bandit_state" not in db_adapter_source and "def persist_bandit_state" not in db_adapter_source
