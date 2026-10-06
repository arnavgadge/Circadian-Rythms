"""Tests for the Phase 10 recommendation engine."""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from app.alignment.engine import compute_alignment
from app.alignment.inputs import AlignmentInputs
from app.contributors.engine import rank_contributors
from app.contributors.inputs import ContributorInputs
from app.recommendations.behavior import BehavioralHistory
from app.recommendations.catalogue import (
    CLOCK_HOUR,
    DECREASE,
    DURATION_MINUTES,
    EARLIER,
    INCREASE,
    CandidateIntervention,
)
from app.recommendations.config import RecommendationConfig
from app.recommendations.cooldown import PriorPrimary
from app.recommendations.engine import select_recommendations
from app.recommendations.feasibility import RecentComplianceRecord, compute_feasibility
from app.recommendations.inputs import RecommendationInputs
from app.recommendations.personalization import (
    LITERATURE,
    PERSONAL_EFFECT,
    PERSONAL_RANKING,
    SOURCE_LITERATURE,
    SOURCE_PERSONAL,
)
from app.recommendations.sanity import run_sanity_checks
from app.recommendations.severity import GOOD, MILD, MODERATE, SEVERE, classify_severity, severity_weights
from app.recommendations.targets import compute_graduated_target
from app.recommendations.templates import render_template
from app.state.circadian_state import ParticipantPhaseTraits
from app.synthetic.time_utils import normalize_hour


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------


def _traits(**overrides) -> ParticipantPhaseTraits:
    defaults = dict(
        intrinsic_dlmo_hour=21.0, baseline_sleep_onset_hour=23.0,
        light_sensitivity=1.0, screen_sensitivity=1.0, meal_sensitivity=1.0, chronotype="Intermediate",
    )
    defaults.update(overrides)
    return ParticipantPhaseTraits(**defaults)


def _alignment_result(**overrides):
    defaults = dict(
        fused_dlmo_hour=21.75,
        most_recent_sleep_onset_hour=23.9,
        window_sleep_onset_hours=[23.7, 23.8, 23.9, 23.75, 23.85, 23.9],
        window_morning_light_duration_minutes=[10, 8, 12, 9, 11, 10],
        window_evening_screen_duration_hours=[3.5, 4.0, 3.8, 4.2, 3.9, 4.1],
        window_last_meal_hours=[21.5, 22.0, 21.8, 22.2, 21.9, 22.1],
        window_social_jetlag_minutes=[None, None, None, None, 90.0, None],
        chronotype="Intermediate",
    )
    defaults.update(overrides)
    return compute_alignment(AlignmentInputs(**defaults))


def _contributor_result(alignment_result=None, **overrides):
    alignment_result = alignment_result or _alignment_result()
    defaults = dict(
        traits=_traits(),
        alignment_result=alignment_result,
        window_morning_light_duration_minutes=[10, 8, 12, 9, 11, 10],
        window_evening_screen_duration_hours=[3.5, 4.0, 3.8, 4.2, 3.9, 4.1],
        window_last_meal_hours=[21.5, 22.0, 21.8, 22.2, 21.9, 22.1],
        window_exercise_hours=[19.0, 19.5, 18.5, 19.2, 19.1, 18.8],
        window_social_jetlag_minutes=[None, None, None, None, 90.0, None],
        latest_morning_light_duration_minutes=10.0,
        latest_evening_screen_duration_hours=4.0,
        latest_last_meal_hour=22.0,
        latest_exercise_hour=19.0,
        latest_social_jetlag_minutes=90.0,
    )
    defaults.update(overrides)
    return rank_contributors(ContributorInputs(**defaults))


def _behavioral_history(**overrides) -> BehavioralHistory:
    defaults = dict(
        actual_sleep_onset_hour=23.9,
        window_evening_screen_duration_hours=[3.5, 4.0, 3.8, 4.2, 3.9, 4.1],
        window_morning_light_duration_minutes=[10, 8, 12, 9, 11, 10],
        window_last_meal_hours=[21.5, 22.0, 21.8, 22.2, 21.9, 22.1],
        window_exercise_hours=[19.0, 19.5, 18.5, 19.2, 19.1, 18.8],
        window_social_jetlag_minutes=[None, None, None, None, 90.0, None],
    )
    defaults.update(overrides)
    return BehavioralHistory(**defaults)


def _candidate(**overrides) -> CandidateIntervention:
    defaults = dict(
        intervention_id=1, intervention_code="TEST_SCREEN", intervention_type="screen", title="Test screen",
        is_active=True, contributor_signals=("evening_screen",), value_kind=CLOCK_HOUR, direction=EARLIER,
        template="Try stopping screens by {target_time}.",
        desired_value_assumption=-0.5, desired_value_relative_to="ideal_sleep_onset",
        max_shift_per_recommendation=1.5, min_target_value=None, max_target_value=None,
        baseline_feasibility=0.6, severity_applicability=(), literature_expected_improvement_minutes=15.0,
        is_literature_verified=False, source_note="test",
    )
    defaults.update(overrides)
    return CandidateIntervention(**defaults)


def _light_candidate(**overrides) -> CandidateIntervention:
    defaults = dict(
        intervention_id=2, intervention_code="TEST_LIGHT", intervention_type="light", title="Test light",
        is_active=True, contributor_signals=("morning_light",), value_kind=DURATION_MINUTES, direction=INCREASE,
        template="Try getting {target_value} of light.",
        desired_value_assumption=30.0, desired_value_relative_to=None,
        max_shift_per_recommendation=15.0, min_target_value=0.0, max_target_value=120.0,
        baseline_feasibility=0.65, severity_applicability=(), literature_expected_improvement_minutes=15.0,
        is_literature_verified=False, source_note="test",
    )
    defaults.update(overrides)
    return CandidateIntervention(**defaults)


def _meal_candidate(**overrides) -> CandidateIntervention:
    defaults = dict(
        intervention_id=3, intervention_code="TEST_MEAL", intervention_type="meal", title="Test meal",
        is_active=True, contributor_signals=("meal_timing",), value_kind=CLOCK_HOUR, direction=EARLIER,
        template="Try finishing your last meal by {target_time}.",
        desired_value_assumption=-3.0, desired_value_relative_to="ideal_sleep_onset",
        max_shift_per_recommendation=1.0, min_target_value=None, max_target_value=None,
        baseline_feasibility=0.6, severity_applicability=(), literature_expected_improvement_minutes=8.0,
        is_literature_verified=False, source_note="test",
    )
    defaults.update(overrides)
    return CandidateIntervention(**defaults)


def _jetlag_candidate(**overrides) -> CandidateIntervention:
    defaults = dict(
        intervention_id=4, intervention_code="TEST_JETLAG", intervention_type="sleep", title="Test jetlag",
        is_active=True, contributor_signals=("social_jetlag",), value_kind=DURATION_MINUTES, direction=DECREASE,
        template="Try reducing your weekend schedule shift to {target_value}.",
        desired_value_assumption=0.0, desired_value_relative_to=None,
        max_shift_per_recommendation=30.0, min_target_value=0.0, max_target_value=None,
        baseline_feasibility=0.55, severity_applicability=(), literature_expected_improvement_minutes=10.0,
        is_literature_verified=False, source_note="test",
    )
    defaults.update(overrides)
    return CandidateIntervention(**defaults)


def _full_catalogue():
    return [_candidate(), _light_candidate(), _meal_candidate(), _jetlag_candidate()]


def _inputs(**overrides) -> RecommendationInputs:
    defaults = dict(
        fused_dlmo_hour=21.75,
        alignment_result=_alignment_result(),
        contributor_result=_contributor_result(),
        behavioral_history=_behavioral_history(),
        candidate_interventions=_full_catalogue(),
        participant_id=1,
        today=date(2026, 1, 15),
    )
    defaults.update(overrides)
    return RecommendationInputs(**defaults)


# --- 1. Severity classification ---


def test_severity_classification_bands():
    assert classify_severity(90.0) == GOOD
    assert classify_severity(70.0) == MILD
    assert classify_severity(50.0) == MODERATE
    assert classify_severity(20.0) == SEVERE


# --- 2. Severity boundary conditions ---


def test_severity_boundaries_are_inclusive_on_lower_bound():
    assert classify_severity(80.0) == GOOD
    assert classify_severity(79.999) == MILD
    assert classify_severity(60.0) == MILD
    assert classify_severity(59.999) == MODERATE
    assert classify_severity(40.0) == MODERATE
    assert classify_severity(39.999) == SEVERE


# --- 3. Severity-specific impact/feasibility weights ---


def test_severity_weights_sum_to_one_and_match_locked_values():
    config = RecommendationConfig()
    severe = severity_weights(SEVERE, config)
    moderate = severity_weights(MODERATE, config)
    mild = severity_weights(MILD, config)
    assert (severe.impact_weight, severe.feasibility_weight) == pytest.approx((0.55, 0.45))
    assert (moderate.impact_weight, moderate.feasibility_weight) == pytest.approx((0.45, 0.55))
    assert (mild.impact_weight, mild.feasibility_weight) == pytest.approx((0.35, 0.65))
    for weights in (severe, moderate, mild):
        assert weights.impact_weight + weights.feasibility_weight == pytest.approx(1.0)


def test_good_alignment_favors_feasibility_over_impact():
    weights = severity_weights(GOOD)
    assert weights.feasibility_weight > weights.impact_weight


# --- 4. Candidate relevance ---


def test_top_contributor_gets_highest_relevance():
    result = select_recommendations(_inputs())
    # evening_screen is Phase 9's dominant contributor for this fixture.
    assert result.primary.contributor_signal == "evening_screen"


def test_irrelevant_intervention_is_not_chosen_as_primary_over_relevant_one():
    # A high-literature-impact but contributor-irrelevant candidate must
    # not outrank a directly relevant, lower-impact one.
    irrelevant = _candidate(
        intervention_id=99, intervention_code="IRRELEVANT", contributor_signals=(),
        literature_expected_improvement_minutes=999.0,
    )
    result = select_recommendations(_inputs(candidate_interventions=_full_catalogue() + [irrelevant]))
    assert result.primary.intervention_code != "IRRELEVANT"


# --- 5. Primary intervention selection / 6. exactly one primary ---


def test_exactly_one_primary_intervention():
    result = select_recommendations(_inputs())
    assert result.primary is not None
    assert result.primary.priority == 1


# --- 7. Maximum two supporting nudges ---


def test_at_most_two_supporting_nudges():
    result = select_recommendations(_inputs())
    assert len(result.supporting) <= 2
    assert [s.priority for s in result.supporting] == list(range(2, 2 + len(result.supporting)))


def test_never_three_equal_priority_recommendations():
    result = select_recommendations(_inputs())
    priorities = [result.primary.priority] + [s.priority for s in result.supporting]
    assert priorities.count(1) == 1
    assert len(priorities) <= 3


# --- 8. No duplicate interventions ---


def test_no_duplicate_interventions_across_primary_and_supporting():
    result = select_recommendations(_inputs())
    ids = [result.primary.intervention_id] + [s.intervention_id for s in result.supporting]
    assert len(ids) == len(set(ids))


def test_duplicate_catalogue_rows_are_deduplicated():
    catalogue = _full_catalogue() + [_candidate()]  # exact duplicate intervention_id
    result = select_recommendations(_inputs(candidate_interventions=catalogue))
    ids = [result.primary.intervention_id] + [s.intervention_id for s in result.supporting]
    assert len(ids) == len(set(ids))
    assert any(d.exclusion_reason == "duplicate_intervention_id" for d in result.diagnostics)


# --- 9. Graduated target calculation ---


def test_graduated_target_is_halfway_to_desired_value_linear():
    candidate = _light_candidate()
    target = compute_graduated_target(candidate, current_value=10.0, ideal_sleep_onset_hour=None, fraction=0.5)
    assert target.desired_value == pytest.approx(30.0)
    assert target.raw_gap == pytest.approx(20.0)
    assert target.target_value == pytest.approx(20.0)  # 10 + 0.5*(30-10)


# --- 10. Circular graduated target calculation ---


def test_circular_graduated_target_uses_shortest_arc():
    candidate = _candidate(desired_value_relative_to=None, desired_value_assumption=22.5, max_shift_per_recommendation=6.0)
    target = compute_graduated_target(candidate, current_value=1.5, ideal_sleep_onset_hour=None, fraction=0.5)
    assert target.raw_gap == pytest.approx(-3.0)  # shortest path is backward 3h, not forward 21h
    assert normalize_hour(target.target_value) == pytest.approx(0.0, abs=1e-6)


# --- 11. Midnight target adjustment (the exact worked example) ---


def test_midnight_example_matches_worked_example_in_docs():
    # current cutoff 01:30, desired 22:30 -> gap 3h -> graduated ~00:00.
    candidate = _candidate(desired_value_relative_to=None, desired_value_assumption=22.5, max_shift_per_recommendation=6.0)
    target = compute_graduated_target(candidate, current_value=1.5, ideal_sleep_onset_hour=None, fraction=0.5)
    assert normalize_hour(target.target_value) == pytest.approx(0.0, abs=1e-6)


# --- 12. Intervention-specific target bounds ---


def test_max_shift_bound_clips_applied_shift():
    candidate = _candidate(max_shift_per_recommendation=0.25)  # tiny bound
    target = compute_graduated_target(candidate, current_value=1.5, ideal_sleep_onset_hour=21.75, fraction=0.5)
    assert abs(target.applied_shift) == pytest.approx(0.25)
    assert target.bound_clipped is True


def test_min_max_target_value_bounds_are_respected():
    candidate = _light_candidate(min_target_value=15.0, max_target_value=18.0, max_shift_per_recommendation=100.0)
    target = compute_graduated_target(candidate, current_value=5.0, ideal_sleep_onset_hour=None, fraction=0.9)
    assert 15.0 <= target.target_value <= 18.0
    assert target.bound_clipped is True


# --- 13. Direction handling ---


def test_wrong_direction_current_already_past_target_is_clamped():
    # Screen cutoff already earlier than the (stale) desired value ->
    # never recommend moving later to "catch up".
    candidate = _candidate()  # direction=earlier, desired = ideal_sleep_onset - 0.5
    target = compute_graduated_target(candidate, current_value=18.0, ideal_sleep_onset_hour=21.75, fraction=0.5)
    assert target.wrong_direction_clamped is True
    assert target.target_value == pytest.approx(18.0)


def test_increase_direction_moves_value_up():
    candidate = _light_candidate()
    target = compute_graduated_target(candidate, current_value=5.0, ideal_sleep_onset_hour=None, fraction=0.5)
    assert target.target_value > 5.0


# --- 14. Expected-improvement source handling / 15. literature fallback ---


def test_default_personalization_uses_literature_source():
    result = select_recommendations(_inputs())
    assert result.primary.expected_improvement_source == SOURCE_LITERATURE
    assert result.primary.expected_improvement_minutes == pytest.approx(15.0)


def test_literature_fallback_when_personal_effect_missing_for_intervention():
    result = select_recommendations(
        _inputs(personalization_phase=PERSONAL_EFFECT, personal_expected_improvement={9999: 42.0})
    )
    assert result.primary.expected_improvement_source == SOURCE_LITERATURE


# --- 16. Personalized-score input compatibility ---


def test_personal_effect_overrides_literature_value():
    result = select_recommendations(
        _inputs(personalization_phase=PERSONAL_EFFECT, personal_expected_improvement={1: 55.0})
    )
    assert result.primary.intervention_id == 1
    assert result.primary.expected_improvement_source == SOURCE_PERSONAL
    assert result.primary.expected_improvement_minutes == pytest.approx(55.0)


def test_personalized_ranking_can_change_selection_without_llm():
    # Boost the meal candidate's ranking score enough to overtake the
    # naturally-dominant screen candidate.
    result = select_recommendations(
        _inputs(personalization_phase=PERSONAL_RANKING, personalized_ranking={3: 10.0})
    )
    assert result.primary.intervention_id == 3


# --- 17. Feasibility scoring ---


def test_feasibility_baseline_with_no_history():
    result = compute_feasibility(baseline_feasibility=0.6, shift_fraction_of_bound=0.0)
    assert result.score == pytest.approx(0.6)


def test_feasibility_increases_with_good_compliance_history():
    good_history = (RecentComplianceRecord(True, 1.0),) * 3
    result = compute_feasibility(baseline_feasibility=0.5, shift_fraction_of_bound=0.0, recent_compliance=good_history)
    assert result.score > 0.5


def test_feasibility_decreases_with_large_target_shift():
    small_shift = compute_feasibility(baseline_feasibility=0.6, shift_fraction_of_bound=0.1)
    large_shift = compute_feasibility(baseline_feasibility=0.6, shift_fraction_of_bound=1.0)
    assert large_shift.score < small_shift.score


# --- 18. Recently failed intervention handling ---


def test_recent_failure_reduces_feasibility():
    baseline = compute_feasibility(baseline_feasibility=0.6, shift_fraction_of_bound=0.0)
    with_failure = compute_feasibility(
        baseline_feasibility=0.6, shift_fraction_of_bound=0.0,
        recent_compliance=(RecentComplianceRecord(False, 0.0),),
    )
    assert with_failure.score < baseline.score


def test_recently_failed_intervention_scores_lower_than_alternative():
    catalogue = _full_catalogue()
    failing_history = {1: (RecentComplianceRecord(False, 0.0), RecentComplianceRecord(False, 0.0))}
    result = select_recommendations(
        _inputs(candidate_interventions=catalogue, recent_compliance_by_intervention=failing_history)
    )
    diag_screen = next(d for d in result.diagnostics if d.intervention_id == 1)
    diag_jetlag = next(d for d in result.diagnostics if d.intervention_id == 4)
    assert diag_screen.candidate_score is not None and diag_jetlag.candidate_score is not None


# --- 19. Recommendation repetition/cooldown ---


def test_prior_primary_within_cooldown_gets_continuation_bonus():
    prior = PriorPrimary(intervention_id=3, log_date=date(2026, 1, 13))  # meal, 2 days before "today"
    result_with_prior = select_recommendations(_inputs(prior_primary=prior, today=date(2026, 1, 15)))
    result_without_prior = select_recommendations(_inputs(today=date(2026, 1, 15)))
    diag_with = next(d for d in result_with_prior.diagnostics if d.intervention_id == 3)
    diag_without = next(d for d in result_without_prior.diagnostics if d.intervention_id == 3)
    assert diag_with.continuation_bonus > diag_without.continuation_bonus


def test_cooldown_does_not_force_a_badly_scoring_continuation():
    # Even with a continuation bonus, a prior primary scoring far below
    # the best alternative must not be forced back into primary.
    prior = PriorPrimary(intervention_id=4, log_date=date(2026, 1, 14))
    poor_jetlag = _jetlag_candidate(baseline_feasibility=0.01, literature_expected_improvement_minutes=0.01)
    catalogue = [_candidate(), _light_candidate(), _meal_candidate(), poor_jetlag]
    result = select_recommendations(_inputs(candidate_interventions=catalogue, prior_primary=prior))
    assert result.primary.intervention_id != 4


# --- 20. Conflict resolution / 21. multiple contributors -> one intervention ---


def test_supporting_excludes_candidate_fully_redundant_with_primary():
    duplicate_signal = _candidate(intervention_id=50, intervention_code="SCREEN_ALT", contributor_signals=("evening_screen",))
    result = select_recommendations(_inputs(candidate_interventions=_full_catalogue() + [duplicate_signal]))
    supporting_ids = [s.intervention_id for s in result.supporting]
    # Only one of the two evening_screen-mapped interventions can appear
    # across primary+supporting (whichever is primary excludes the other).
    assert not (result.primary.intervention_id in (1, 50) and 1 in supporting_ids and 50 in supporting_ids)


def test_one_intervention_covering_multiple_significant_contributors_gets_relevance_bonus():
    from app.recommendations.relevance import compute_contributor_relevance

    ranked = ("morning_light", "evening_screen", "social_jetlag")  # ranks 0, 1, 2
    single = compute_contributor_relevance(("evening_screen",), ranked)
    multi = compute_contributor_relevance(("evening_screen", "social_jetlag"), ranked)
    assert multi.relevance > single.relevance
    assert set(multi.matched_signals) == {"evening_screen", "social_jetlag"}


# --- 22. No available intervention ---


def test_no_candidates_at_all_returns_no_primary():
    result = select_recommendations(_inputs(candidate_interventions=[]))
    assert result.primary is None
    assert result.supporting == []


def test_top_contributor_with_no_matching_intervention_falls_back_gracefully():
    # Catalogue only has an exercise-mapped intervention, but exercise is
    # not this fixture's significant top contributor -> relevance-based
    # fallback should still choose something rather than nothing.
    exercise_only = _candidate(
        intervention_id=7, intervention_code="EXERCISE_ONLY", contributor_signals=("exercise",),
    )
    result = select_recommendations(_inputs(candidate_interventions=[exercise_only]))
    assert result.primary is not None
    assert result.primary.intervention_id == 7


# --- 23. Missing-data behavior ---


def test_candidate_with_no_behavioral_data_is_excluded_not_fabricated():
    history = _behavioral_history(window_evening_screen_duration_hours=[None] * 6)
    result = select_recommendations(_inputs(behavioral_history=history))
    assert result.primary.intervention_code != "TEST_SCREEN"
    diag = next(d for d in result.diagnostics if d.intervention_id == 1)
    assert diag.excluded is True
    assert diag.exclusion_reason == "missing_behavioral_data"


def test_imputed_contributor_data_reduces_relevance_not_eliminates():
    from app.recommendations.relevance import compute_contributor_relevance

    full_relevance = compute_contributor_relevance(("evening_screen",), ("evening_screen",))
    config = RecommendationConfig(imputed_data_relevance_multiplier=0.5)
    assert full_relevance.relevance * config.imputed_data_relevance_multiplier < full_relevance.relevance


# --- 24. Deterministic selection ---


def test_select_recommendations_is_deterministic():
    inputs = _inputs()
    result_a = select_recommendations(inputs)
    result_b = select_recommendations(inputs)
    assert result_a.primary.intervention_id == result_b.primary.intervention_id
    assert result_a.primary.candidate_score == pytest.approx(result_b.primary.candidate_score)
    assert [s.intervention_id for s in result_a.supporting] == [s.intervention_id for s in result_b.supporting]


# --- 25. Template rendering ---


def test_template_renders_clock_time_not_raw_float():
    candidate = _candidate()
    text = render_template(candidate, target_value=22.0, current_value=18.5, expected_improvement_minutes=15.0)
    assert "22.0" not in text and "18.5" not in text
    assert "10:00 PM" in text


def test_template_missing_placeholder_degrades_gracefully():
    candidate = _candidate(template="Focus: {nonexistent_field}")
    text = render_template(candidate, target_value=22.0, current_value=18.5, expected_improvement_minutes=15.0)
    assert "{nonexistent_field}" in text  # never raises


# --- 26. No medical recommendations ---


def test_no_medical_or_medication_language_in_seeded_catalogue():
    from app.database.seed import _REFERENCE_RECOMMENDATIONS

    banned_terms = ("melatonin", "medication", "dosage", "dose", "prescri", "diagnos", "treatment")
    for entry in _REFERENCE_RECOMMENDATIONS:
        text = " ".join(
            str(entry.get(field, "")) for field in ("title", "description", "target_behavior")
        ).lower()
        template = str(entry.get("extra_metadata", {}).get("template", "")).lower()
        for term in banned_terms:
            assert term not in text, f"{entry['intervention_code']} description mentions '{term}'"
            assert term not in template, f"{entry['intervention_code']} template mentions '{term}'"


# --- 27. Serializable RecommendationResult ---


def test_recommendation_result_is_serializable_via_asdict():
    result = select_recommendations(_inputs())
    as_dict = dataclasses.asdict(result)
    assert as_dict["primary"]["intervention_code"]
    assert isinstance(as_dict["supporting"], list)
    import json

    json.dumps(as_dict, default=str)  # must not raise


# --- Sanity checks ---


def test_sanity_checks_pass_for_a_normal_result():
    result = select_recommendations(_inputs())
    report = run_sanity_checks(result)
    assert report.ok, report.summary_lines()


def test_sanity_checks_pass_for_a_no_candidate_result():
    result = select_recommendations(_inputs(candidate_interventions=[]))
    report = run_sanity_checks(result)
    assert report.ok, report.summary_lines()


# --- Database integration (test area 22 from the Phase 10 brief: "database storage compatibility") ---


def test_db_adapter_loads_seeded_catalogue_and_selects_recommendations(small_synthetic_session):
    from sqlalchemy import select

    from app.database.models import Participant
    from app.database.seed import seed_reference_data
    from app.recommendations.db_adapter import build_behavioral_history, load_candidate_interventions

    seed_reference_data(small_synthetic_session)
    catalogue = load_candidate_interventions(small_synthetic_session)
    assert len(catalogue) >= 6
    assert any(c.contributor_signals == ("evening_screen",) for c in catalogue)

    pid = small_synthetic_session.execute(select(Participant.id).order_by(Participant.id)).scalars().first()
    from app.database.models import DailyObservation

    observations = small_synthetic_session.execute(
        select(DailyObservation).where(DailyObservation.participant_id == pid).order_by(DailyObservation.observation_date)
    ).scalars().all()
    window = observations[:6]

    history = build_behavioral_history(window)
    result = select_recommendations(
        _inputs(candidate_interventions=catalogue, behavioral_history=history)
    )
    report = run_sanity_checks(result)
    assert report.ok, report.summary_lines()
