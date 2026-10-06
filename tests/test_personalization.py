"""Pure-logic tests for the Phase 13 personalization system (no
database) -- DB-integration tests live in ``test_personalization_db.py``.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from app.personalization.bandit import ArmPosterior, prior_arm, select_action, thompson_sample, update_posterior
from app.personalization.blending import SOURCE_BLENDED, SOURCE_LITERATURE, SOURCE_PERSONAL, blend_effect
from app.personalization.compliance_probability import estimate_compliance_probability
from app.personalization.config import DEFAULT_PERSONALIZATION_CONFIG, PersonalizationConfig
from app.personalization.context import build_context
from app.personalization.effect_model import build_personal_effect_model, predict_effect
from app.personalization.explain import explain_adaptive, explain_literature, explain_personal_effect, explain_personal_ranking
from app.personalization.phases import (
    EVIDENCE_EMERGING,
    EVIDENCE_INSUFFICIENT,
    EVIDENCE_STRONGER,
    EVIDENCE_WEAK,
    classify_evidence_strength,
    phase_from_evidence,
)
from app.personalization.ranking import compute_personal_ranking_entry, rank_candidates
from app.personalization.reward import compute_reward
from app.personalization.validity import check_model_validity
from app.recommendations.personalization import ADAPTIVE_POLICY, LITERATURE, PERSONAL_EFFECT, PERSONAL_RANKING


# --- 1. Cold-start literature fallback ---


def test_cold_start_returns_literature():
    assert phase_from_evidence(0, 0.0) == LITERATURE


# --- 2. Personal-ranking activation ---


def test_personal_ranking_activates_at_configured_minimums():
    config = DEFAULT_PERSONALIZATION_CONFIG
    assert phase_from_evidence(config.ranking_min_observations, config.ranking_min_weeks_active, config) == PERSONAL_RANKING
    assert phase_from_evidence(config.ranking_min_observations - 1, config.ranking_min_weeks_active, config) == LITERATURE
    assert phase_from_evidence(config.ranking_min_observations, config.ranking_min_weeks_active - 1, config) == LITERATURE


# --- 5. Personal-effect activation ---


def test_personal_effect_activates_at_configured_minimums():
    config = DEFAULT_PERSONALIZATION_CONFIG
    assert phase_from_evidence(config.effect_model_min_observations, config.effect_model_min_weeks_active, config) == PERSONAL_EFFECT


def test_adaptive_policy_activates_at_configured_minimums():
    config = DEFAULT_PERSONALIZATION_CONFIG
    assert phase_from_evidence(config.adaptive_min_observations, config.adaptive_min_weeks_active, config) == ADAPTIVE_POLICY


# --- evidence strength labeling ---


def test_evidence_strength_labels():
    assert classify_evidence_strength(0) == EVIDENCE_INSUFFICIENT
    assert classify_evidence_strength(5) == EVIDENCE_WEAK
    assert classify_evidence_strength(10) == EVIDENCE_EMERGING
    assert classify_evidence_strength(30) == EVIDENCE_STRONGER


# --- 3. Personal-ranking calculation ---


def test_personal_ranking_score_is_effect_times_compliance():
    entry = compute_personal_ranking_entry(
        "screen", literature_effect=15.0, effect_estimate_measurement_phase=3, effect_estimate_value=-10.0,
        n_observations=25, historical_compliance_degrees=[0.8, 0.9, 0.7],
    )
    assert entry.personal_effect == pytest.approx(-10.0)
    assert entry.compliance_probability == pytest.approx(0.8, abs=0.01)
    assert entry.personal_score == pytest.approx(10.0 * entry.compliance_probability)
    assert entry.evidence_source == "phase3_regression"


def test_personal_ranking_falls_back_to_literature_when_evidence_thin():
    entry = compute_personal_ranking_entry(
        "screen", literature_effect=15.0, effect_estimate_measurement_phase=None, effect_estimate_value=None,
        n_observations=1, historical_compliance_degrees=[],
    )
    assert entry.personal_effect == pytest.approx(15.0)
    assert entry.evidence_source == "literature"
    assert entry.compliance_probability is None
    assert entry.personal_score is None  # cannot compute without a compliance probability


def test_rank_candidates_sorts_descending_and_unrankable_last():
    entries = [
        SimpleNamespace(personal_score=5.0), SimpleNamespace(personal_score=None), SimpleNamespace(personal_score=12.0),
    ]
    ranked = rank_candidates(entries)
    assert [e.personal_score for e in ranked] == [12.0, 5.0, None]


# --- 4. Compliance probability calculation ---


def test_compliance_probability_is_mean_of_history():
    assert estimate_compliance_probability([1.0, 0.5, 0.0]) == pytest.approx(0.5)
    assert estimate_compliance_probability([]) is None


# --- 6, 7, 8, 9. Blending ---


def test_blend_uses_blended_weights_below_full_personal_threshold():
    result = blend_effect(literature_effect=15.0, personal_effect=-10.0, n_observations=10, personal_model_valid=True)
    expected = 0.40 * -10.0 + 0.60 * 15.0
    assert result.value == pytest.approx(expected)
    assert result.source == SOURCE_BLENDED


def test_blend_uses_full_personal_above_threshold():
    config = DEFAULT_PERSONALIZATION_CONFIG
    result = blend_effect(15.0, -10.0, config.full_personal_min_observations, True, config)
    assert result.value == pytest.approx(-10.0)
    assert result.source == SOURCE_PERSONAL


def test_blend_falls_back_to_literature_when_no_personal_effect():
    result = blend_effect(15.0, None, 30, True)
    assert result.value == pytest.approx(15.0)
    assert result.source == SOURCE_LITERATURE


def test_blend_falls_back_to_literature_when_model_invalid():
    result = blend_effect(15.0, -999.0, 30, personal_model_valid=False)
    assert result.value == pytest.approx(15.0)
    assert result.source == SOURCE_LITERATURE


# --- 10. Effect-model fitting / 12. confidence interval handling ---


def _fake_estimate(measurement_phase=3, effect_estimate=-10.0, r_squared=0.9, n_observations=25, ci_lower=-14.0, ci_upper=-6.0, intercept=1.5):
    return SimpleNamespace(
        measurement_phase=measurement_phase, effect_estimate=effect_estimate, r_squared=r_squared,
        n_observations=n_observations, confidence_interval_lower=ci_lower, confidence_interval_upper=ci_upper,
        diagnostics={"coefficients": {"intercept": intercept}},
    )


def test_build_personal_effect_model_extracts_phase3_coefficients():
    estimate = _fake_estimate()
    result = build_personal_effect_model("screen", estimate, [0.1, 0.5, 0.9, 0.3, 0.8, 0.2, 0.95, 0.4, 0.6, 0.7, 0.15, 0.85, 0.25, 0.75])
    assert result.slope == pytest.approx(-10.0)
    assert result.intercept == pytest.approx(1.5)
    assert result.confidence_interval_lower == pytest.approx(-14.0)
    assert result.confidence_interval_upper == pytest.approx(-6.0)
    assert result.validity.valid


def test_build_personal_effect_model_insufficient_without_phase3():
    result = build_personal_effect_model("screen", None, [])
    assert result.evidence_source == "insufficient"
    assert not result.validity.valid
    assert result.slope is None


def test_predict_effect_uses_the_line_equation():
    assert predict_effect(slope=-10.0, intercept=2.0, compliance=0.8) == pytest.approx(-6.0)
    assert predict_effect(None, 2.0, 0.8) is None


# --- 11. Model validity checks ---


def test_model_validity_flags_implausible_magnitude():
    result = check_model_validity(
        slope=500.0, intercept=0.0, r_squared=0.9, n_observations=30,
        confidence_interval_lower=-10, confidence_interval_upper=10,
        compliance_values=[0.1, 0.9, 0.2, 0.8, 0.3, 0.7],
    )
    assert not result.valid
    assert "implausible_effect_magnitude" in result.reasons


def test_model_validity_flags_degenerate_compliance():
    result = check_model_validity(
        slope=-10.0, intercept=0.0, r_squared=0.9, n_observations=30,
        confidence_interval_lower=-14, confidence_interval_upper=-6,
        compliance_values=[0.5] * 20,  # zero variance
    )
    assert not result.valid
    assert "degenerate_compliance_values" in result.reasons


def test_model_validity_passes_for_reasonable_model():
    result = check_model_validity(
        slope=-10.0, intercept=1.0, r_squared=0.9, n_observations=30,
        confidence_interval_lower=-14, confidence_interval_upper=-6,
        compliance_values=[0.1, 0.9, 0.2, 0.8, 0.3, 0.7],
    )
    assert result.valid
    assert result.reasons == ()


# --- 17. Personal target adjustment ---


def test_target_aggressiveness_unchanged_for_literature_and_ranking():
    from app.personalization.targeting import adjust_target_aggressiveness

    assert adjust_target_aggressiveness(0.5, LITERATURE, 1.0) == pytest.approx(0.5)
    assert adjust_target_aggressiveness(0.5, PERSONAL_RANKING, 1.0) == pytest.approx(0.5)


def test_target_aggressiveness_bounded_adjustment_for_personal_effect():
    config = DEFAULT_PERSONALIZATION_CONFIG
    from app.personalization.targeting import adjust_target_aggressiveness

    increased = adjust_target_aggressiveness(0.5, PERSONAL_EFFECT, 1.0, config)
    decreased = adjust_target_aggressiveness(0.5, PERSONAL_EFFECT, -1.0, config)
    assert increased == pytest.approx(0.5 + config.max_target_aggressiveness_adjustment)
    assert decreased == pytest.approx(0.5 - config.max_target_aggressiveness_adjustment)


# --- 19. Contextual feature construction ---


def test_build_context_is_a_small_interpretable_struct():
    ctx = build_context(
        current_dlmo_hour=21.5, alignment_score=60.0, top_contributor_signal="evening_screen",
        day_of_week=2, upcoming_free_days=2, recent_compliance_rate=0.7, weeks_active=5.0, current_severity="moderate",
    )
    assert ctx.top_contributor_signal == "evening_screen"
    assert ctx.current_severity == "moderate"


# --- 20. Bandit state update / 24. reward calculation / 25. cold-start bandit fallback ---


def test_cold_start_bandit_uses_configured_prior():
    config = DEFAULT_PERSONALIZATION_CONFIG
    arm = prior_arm("morning_light", config)
    assert arm.posterior_mean == pytest.approx(config.bandit_prior_mean)
    assert arm.posterior_variance == pytest.approx(config.bandit_prior_variance)
    assert arm.total_pulls == 0


def test_update_posterior_moves_mean_toward_reward():
    arm = ArmPosterior("morning_light", posterior_mean=0.0, posterior_variance=100.0, total_pulls=0, total_reward=0.0)
    updated = update_posterior(arm, reward=20.0)
    assert 0.0 < updated.posterior_mean < 20.0
    assert updated.posterior_variance < arm.posterior_variance  # uncertainty shrinks with evidence
    assert updated.total_pulls == 1
    assert updated.total_reward == pytest.approx(20.0)


def test_reward_positive_when_effect_is_corrective():
    # Too delayed (needs advance); an advancing (negative) effect helps.
    reward = compute_reward(signed_effect_minutes=-10.0, phase_deviation_minutes=60.0, compliance=1.0)
    assert reward > 0


def test_reward_negative_when_effect_aggravates():
    reward = compute_reward(signed_effect_minutes=10.0, phase_deviation_minutes=60.0, compliance=1.0)
    assert reward < 0


def test_reward_scales_with_compliance():
    full = compute_reward(-10.0, 60.0, 1.0)
    half = compute_reward(-10.0, 60.0, 0.5)
    assert half == pytest.approx(full / 2)


def test_reward_none_when_deviation_missing():
    assert compute_reward(-10.0, None, 1.0) is None


# --- 21. Thompson sampling behavior ---


def test_thompson_sampling_favors_higher_mean_arm_over_many_draws():
    rng = np.random.default_rng(42)
    strong = ArmPosterior("A", posterior_mean=20.0, posterior_variance=25.0, total_pulls=50, total_reward=1000.0)
    weak = ArmPosterior("B", posterior_mean=2.0, posterior_variance=25.0, total_pulls=50, total_reward=100.0)

    wins = {"A": 0, "B": 0}
    for _ in range(500):
        chosen, _ = select_action([strong, weak], rng, DEFAULT_PERSONALIZATION_CONFIG)
        wins[chosen] += 1

    assert wins["A"] > wins["B"]


# --- 22. Exploration safeguards ---


def test_exploration_never_overrides_a_dominant_arm():
    rng = np.random.default_rng(1)
    dominant = ArmPosterior("A", posterior_mean=100.0, posterior_variance=1.0, total_pulls=100, total_reward=10000.0)
    longshot = ArmPosterior("B", posterior_mean=0.0, posterior_variance=10000.0, total_pulls=1, total_reward=0.0)

    for _ in range(50):
        chosen, _ = select_action([dominant, longshot], rng, DEFAULT_PERSONALIZATION_CONFIG)
        assert chosen == "A"  # never displaced despite B's huge variance


# --- 26. Deterministic behavior ---


def test_phase_from_evidence_is_deterministic():
    assert phase_from_evidence(10, 4.0) == phase_from_evidence(10, 4.0)


def test_thompson_sample_is_deterministic_given_seeded_rng():
    rng1 = np.random.default_rng(7)
    rng2 = np.random.default_rng(7)
    arm = ArmPosterior("A", 5.0, 10.0, 1, 5.0)
    draw1 = thompson_sample(arm, rng1)
    draw2 = thompson_sample(arm, rng2)
    assert draw1.sampled_value == pytest.approx(draw2.sampled_value)


# --- Explainability (no LLM, fixed strings) ---


def test_explanations_are_fixed_strings_not_generated():
    assert explain_literature() == "Based on circadian research."
    assert explain_personal_ranking() == "Based on your recent response history."
    assert "morning_light" in explain_personal_effect("morning_light")
    assert explain_adaptive() == "Selected based on your recent response and current context."
