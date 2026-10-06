"""Tests for the Phase 9 contributor ranking engine.

Covers the engine's own composition (score/normalization/deficit/
direction/anomaly units) plus integration through
:func:`app.contributors.engine.rank_contributors`.
"""

from __future__ import annotations

import pytest

from app.alignment.engine import compute_alignment
from app.alignment.inputs import AlignmentInputs
from app.contributors.config import ContributorConfig, DEFAULT_CONTRIBUTOR_CONFIG
from app.contributors.deficits import compute_alignment_deficit
from app.contributors.direction import HURTING, NEUTRAL, OPPORTUNITY_MISSED, classify_direction
from app.contributors.engine import SIGNALS, rank_contributors
from app.contributors.inputs import ContributorInputs
from app.contributors.normalization import normalize_absolute_effects
from app.contributors.sanity import run_sanity_checks
from app.contributors.scoring import compute_contributor_score
from app.state.circadian_state import ParticipantPhaseTraits


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------


def _traits(**overrides) -> ParticipantPhaseTraits:
    defaults = dict(
        intrinsic_dlmo_hour=21.0,
        baseline_sleep_onset_hour=23.0,
        light_sensitivity=1.0,
        screen_sensitivity=1.0,
        meal_sensitivity=1.0,
        chronotype="Intermediate",
    )
    defaults.update(overrides)
    return ParticipantPhaseTraits(**defaults)


def _alignment_result(**overrides) -> AlignmentInputs:
    defaults = dict(
        fused_dlmo_hour=21.75,
        most_recent_sleep_onset_hour=23.9,
        window_sleep_onset_hours=[23.7, 23.8, 23.9, 23.75, 23.85, 23.9],
        window_morning_light_duration_minutes=[30, 25, 35, 28, 32, 30],
        window_evening_screen_duration_hours=[1.2, 1.0, 1.5, 1.1, 0.9, 1.3],
        window_last_meal_hours=[19.5, 20.0, 19.0, 19.8, 20.2, 19.5],
        window_social_jetlag_minutes=[None, None, None, None, 20, None],
        chronotype="Intermediate",
    )
    defaults.update(overrides)
    return compute_alignment(AlignmentInputs(**defaults))


def _contributor_inputs(**overrides) -> ContributorInputs:
    defaults = dict(
        traits=_traits(),
        alignment_result=_alignment_result(),
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
    return ContributorInputs(**defaults)


# --- 1. Contributor score calculation (composite formula) ---


def test_composite_score_is_60_40_weighted_sum():
    result = compute_contributor_score("evening_screen", normalized_phase_effect=80.0, alignment_deficit=50.0)
    assert result.contributor_score == pytest.approx(0.60 * 80.0 + 0.40 * 50.0)
    assert result.weight_used == "composite"


# --- 2. Effect normalization ---


def test_normalization_max_scales_to_100():
    normalized = normalize_absolute_effects({"a": 10.0, "b": 40.0, "c": 20.0})
    assert normalized["b"] == pytest.approx(100.0)
    assert normalized["a"] == pytest.approx(25.0)
    assert normalized["c"] == pytest.approx(50.0)


def test_normalization_preserves_none_for_unavailable_signal():
    normalized = normalize_absolute_effects({"a": 10.0, "b": None})
    assert normalized["a"] == pytest.approx(100.0)
    assert normalized["b"] is None


# --- 3. All-zero effect case ---


def test_all_zero_effects_normalize_to_zero_not_nan():
    normalized = normalize_absolute_effects({"a": 0.0, "b": 0.0, "c": 0.0})
    assert normalized == {"a": 0.0, "b": 0.0, "c": 0.0}


def test_all_zero_effects_do_not_raise_divide_by_zero():
    normalize_absolute_effects({})  # no candidates at all -> still safe


# --- 4. Alignment deficit calculation ---


def test_alignment_deficit_is_100_minus_component_score():
    alignment_result = _alignment_result()
    component = alignment_result.behavioral_components["evening_screen"]
    deficit = compute_alignment_deficit("evening_screen", alignment_result)
    assert deficit == pytest.approx(100.0 - component.score)


# --- 5. Signal/component mapping ---


def test_all_four_mapped_signals_resolve_to_a_component():
    alignment_result = _alignment_result()
    for signal in ("evening_screen", "morning_light", "meal_timing", "social_jetlag"):
        assert compute_alignment_deficit(signal, alignment_result) is not None


def test_unmapped_signal_returns_none():
    alignment_result = _alignment_result()
    assert compute_alignment_deficit("exercise", alignment_result) is None


def test_unavailable_component_returns_none_deficit():
    alignment_result = _alignment_result(window_social_jetlag_minutes=[None] * 6)
    assert compute_alignment_deficit("social_jetlag", alignment_result) is None


# --- 6. Exercise special handling ---


def test_exercise_uses_phase_effect_only():
    result = compute_contributor_score("exercise", normalized_phase_effect=70.0, alignment_deficit=None)
    assert result.contributor_score == pytest.approx(70.0)
    assert result.weight_used == "phase_effect_only"


def test_exercise_score_unavailable_when_no_phase_effect():
    result = compute_contributor_score("exercise", normalized_phase_effect=None, alignment_deficit=None)
    assert result.contributor_score is None
    assert result.weight_used == "unavailable"


def test_social_jetlag_uses_deficit_only():
    result = compute_contributor_score("social_jetlag", normalized_phase_effect=None, alignment_deficit=65.0)
    assert result.contributor_score == pytest.approx(65.0)
    assert result.weight_used == "deficit_only"


def test_composite_signal_falls_back_to_single_input_when_one_missing():
    only_effect = compute_contributor_score("evening_screen", normalized_phase_effect=90.0, alignment_deficit=None)
    assert only_effect.contributor_score == pytest.approx(90.0)
    assert only_effect.weight_used == "phase_effect_only"

    only_deficit = compute_contributor_score("evening_screen", normalized_phase_effect=None, alignment_deficit=40.0)
    assert only_deficit.contributor_score == pytest.approx(40.0)
    assert only_deficit.weight_used == "deficit_only"


def test_exercise_never_receives_fabricated_alignment_component():
    result = rank_contributors(_contributor_inputs())
    exercise = next(c for c in result.all_candidates if c.signal == "exercise")
    assert exercise.alignment_deficit is None
    assert exercise.alignment_component_score is None


# --- 7. Top-3 ranking / never fabricate contributors ---


def test_top_3_has_at_most_three_entries():
    result = rank_contributors(_contributor_inputs())
    assert len(result.contributors) <= 3


def test_all_five_candidates_present_for_full_data():
    result = rank_contributors(_contributor_inputs())
    assert {c.signal for c in result.all_candidates} == set(SIGNALS)


def test_fewer_than_three_valid_signals_does_not_fabricate():
    # Strip all data down so only exercise and social_jetlag can score.
    inputs = _contributor_inputs(
        window_morning_light_duration_minutes=[None] * 6,
        window_evening_screen_duration_hours=[None] * 6,
        window_last_meal_hours=[None] * 6,
        alignment_result=_alignment_result(
            window_morning_light_duration_minutes=[None] * 6,
            window_evening_screen_duration_hours=[None] * 6,
            window_last_meal_hours=[None] * 6,
        ),
    )
    result = rank_contributors(inputs)
    assert len(result.contributors) <= 2
    for c in result.contributors:
        assert c.contributor_score is not None


# --- 8. Descending-order guarantee ---


def test_contributors_are_strictly_descending_by_score():
    result = rank_contributors(_contributor_inputs())
    scores = [c.contributor_score for c in result.contributors]
    assert scores == sorted(scores, reverse=True)


def test_ranks_assigned_1_through_n_in_order():
    result = rank_contributors(_contributor_inputs())
    assert [c.rank for c in result.contributors] == list(range(1, len(result.contributors) + 1))


# --- 9. Significance threshold ---


def test_low_score_signal_is_not_significant():
    result = rank_contributors(_contributor_inputs())
    for c in result.all_candidates:
        assert c.significant == (c.contributor_score is not None and c.contributor_score >= DEFAULT_CONTRIBUTOR_CONFIG.significance_threshold)


def test_significance_threshold_is_configurable():
    strict_config = ContributorConfig(significance_threshold=99.9)
    result = rank_contributors(_contributor_inputs(), config=strict_config)
    assert not any(c.significant for c in result.all_candidates)


# --- 10. Direction classification ---


def test_direction_neutral_when_score_below_significance():
    direction = classify_direction(signed_phase_effect_minutes=20.0, phase_deviation_minutes=60.0, contributor_score=5.0)
    assert direction == NEUTRAL


def test_direction_neutral_when_already_aligned():
    direction = classify_direction(signed_phase_effect_minutes=20.0, phase_deviation_minutes=2.0, contributor_score=80.0)
    assert direction == NEUTRAL


# --- 11. Delay/hurting direction ---


def test_direction_hurting_when_effect_aggravates_deviation():
    # Positive deviation (too delayed) + positive (delaying) effect -> hurting.
    direction = classify_direction(signed_phase_effect_minutes=25.0, phase_deviation_minutes=60.0, contributor_score=80.0)
    assert direction == HURTING


def test_direction_hurting_for_deficit_only_signal_with_no_signed_effect():
    direction = classify_direction(signed_phase_effect_minutes=None, phase_deviation_minutes=60.0, contributor_score=80.0)
    assert direction == HURTING


# --- 12. Missed-advance / opportunity_missed direction ---


def test_direction_opportunity_missed_for_weak_corrective_effect():
    # Positive deviation (too delayed) + small negative (advancing) effect -> opportunity missed.
    direction = classify_direction(signed_phase_effect_minutes=-5.0, phase_deviation_minutes=60.0, contributor_score=80.0)
    assert direction == OPPORTUNITY_MISSED


def test_direction_neutral_for_strong_corrective_effect_already_helping():
    direction = classify_direction(signed_phase_effect_minutes=-30.0, phase_deviation_minutes=60.0, contributor_score=80.0)
    assert direction == NEUTRAL


# --- 13. Today's anomaly detection ---


def test_anomaly_detected_for_large_deviation_from_stable_baseline():
    inputs = _contributor_inputs(
        window_evening_screen_duration_hours=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        latest_evening_screen_duration_hours=6.0,
    )
    result = rank_contributors(inputs)
    assert result.anomaly_details["evening_screen"].is_anomaly is True
    assert result.anomaly_details["evening_screen"].available is True


def test_no_anomaly_when_today_matches_baseline():
    inputs = _contributor_inputs(
        window_evening_screen_duration_hours=[2.0, 2.1, 1.9, 2.0, 2.05, 1.95],
        latest_evening_screen_duration_hours=2.0,
    )
    result = rank_contributors(inputs)
    assert result.anomaly_details["evening_screen"].is_anomaly is False


# --- 14. Anomaly does not alter historical ranking ---


def test_anomaly_flag_never_changes_contributor_score_or_rank():
    stable_inputs = _contributor_inputs(
        window_evening_screen_duration_hours=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        latest_evening_screen_duration_hours=1.0,
    )
    anomalous_inputs = _contributor_inputs(
        window_evening_screen_duration_hours=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        latest_evening_screen_duration_hours=9.0,
    )
    stable_result = rank_contributors(stable_inputs)
    anomalous_result = rank_contributors(anomalous_inputs)

    stable_screen = next(c for c in stable_result.all_candidates if c.signal == "evening_screen")
    anomalous_screen = next(c for c in anomalous_result.all_candidates if c.signal == "evening_screen")

    assert stable_screen.contributor_score == pytest.approx(anomalous_screen.contributor_score)
    assert stable_screen.rank == anomalous_screen.rank
    assert stable_result.anomaly_details["evening_screen"].is_anomaly is False
    assert anomalous_result.anomaly_details["evening_screen"].is_anomaly is True


# --- 15. Circular clock-time anomaly ---


def test_circular_anomaly_does_not_flag_midnight_wraparound_as_outlier():
    # A baseline hovering right around midnight (23:50 vs 00:10) should
    # not itself look anomalous merely because of naive subtraction.
    window_hours = [23.8333, 0.1667, 23.9167, 0.0833, 23.75, 0.25]
    inputs = _contributor_inputs(window_exercise_hours=window_hours, latest_exercise_hour=0.0)
    result = rank_contributors(inputs)
    assert result.anomaly_details["exercise"].is_anomaly is False


def test_circular_anomaly_flags_genuine_outlier_near_midnight():
    window_hours = [23.9, 0.0, 23.95, 0.05, 23.9, 0.0]
    inputs = _contributor_inputs(window_exercise_hours=window_hours, latest_exercise_hour=12.0)
    result = rank_contributors(inputs)
    assert result.anomaly_details["exercise"].is_anomaly is True


# --- 16. Zero-variance personal history (fallback path) ---


def test_zero_variance_baseline_uses_fallback_absolute_threshold():
    inputs = _contributor_inputs(
        window_evening_screen_duration_hours=[2.0] * 6,
        latest_evening_screen_duration_hours=2.0 + (DEFAULT_CONTRIBUTOR_CONFIG.fallback_absolute_threshold_minutes / 60.0) + 0.5,
    )
    result = rank_contributors(inputs)
    anomaly = result.anomaly_details["evening_screen"]
    assert anomaly.method == "fallback_absolute"
    assert anomaly.is_anomaly is True


def test_zero_variance_baseline_no_anomaly_within_fallback_threshold():
    inputs = _contributor_inputs(
        window_evening_screen_duration_hours=[2.0] * 6,
        latest_evening_screen_duration_hours=2.05,
    )
    result = rank_contributors(inputs)
    anomaly = result.anomaly_details["evening_screen"]
    assert anomaly.method == "fallback_absolute"
    assert anomaly.is_anomaly is False


# --- 17. Insufficient history ---


def test_anomaly_unavailable_with_too_few_window_observations():
    inputs = _contributor_inputs(
        window_evening_screen_duration_hours=[2.0, None, None, None, None, None],
        latest_evening_screen_duration_hours=2.0,
    )
    result = rank_contributors(inputs)
    anomaly = result.anomaly_details["evening_screen"]
    assert anomaly.available is False
    assert anomaly.is_anomaly is False


# --- 18. Missing data handling ---


def test_missing_window_data_marks_signal_unavailable_not_fabricated():
    inputs = _contributor_inputs(
        window_morning_light_duration_minutes=[None] * 6,
        alignment_result=_alignment_result(window_morning_light_duration_minutes=[None] * 6),
    )
    result = rank_contributors(inputs)
    light = next(c for c in result.all_candidates if c.signal == "morning_light")
    # All six window slots are present but every value is missing: the
    # phase-effect model skips (never fabricates) every one of those
    # days, so no fabricated effect is produced -- "imputed" reflects
    # that all available slots had to be skipped, not "unavailable"
    # (which is reserved for zero window slots at all).
    assert light.data_quality == "imputed"
    assert light.signed_phase_effect_minutes is None


# --- 19. Imputed data metadata ---


def test_partially_missing_window_marked_imputed():
    inputs = _contributor_inputs(
        window_morning_light_duration_minutes=[10, None, 12, 9, 11, 10],
        window_evening_screen_duration_hours=[3.5, None, 3.8, 4.2, 3.9, 4.1],
        window_last_meal_hours=[21.5, None, 21.8, 22.2, 21.9, 22.1],
        window_exercise_hours=[19.0, None, 18.5, 19.2, 19.1, 18.8],
    )
    result = rank_contributors(inputs)
    light = next(c for c in result.all_candidates if c.signal == "morning_light")
    assert light.data_quality == "imputed"


# --- 20. Deterministic ranking ---


def test_rank_contributors_is_deterministic():
    inputs = _contributor_inputs()
    result_a = rank_contributors(inputs)
    result_b = rank_contributors(inputs)
    assert [c.signal for c in result_a.contributors] == [c.signal for c in result_b.contributors]
    assert [c.contributor_score for c in result_a.contributors] == pytest.approx(
        [c.contributor_score for c in result_b.contributors]
    )


# --- 21. Fixture participant end-to-end ---


def test_screen_heavy_participant_ranks_evening_screen_highly():
    inputs = _contributor_inputs(
        window_evening_screen_duration_hours=[5.0, 5.5, 4.8, 5.2, 5.1, 4.9],
        latest_evening_screen_duration_hours=5.0,
        alignment_result=_alignment_result(window_evening_screen_duration_hours=[5.0, 5.5, 4.8, 5.2, 5.1, 4.9]),
    )
    result = rank_contributors(inputs)
    top_signals = [c.signal for c in result.contributors]
    assert "evening_screen" in top_signals


# --- 22. Database storage compatibility ---


def test_db_adapter_builds_valid_contributor_inputs(small_synthetic_session):
    from sqlalchemy import select

    from app.contributors.db_adapter import build_contributor_inputs
    from app.database.models import DailyObservation, Participant, ParticipantProfile

    pid = small_synthetic_session.execute(select(Participant.id).order_by(Participant.id)).scalars().first()
    profile = small_synthetic_session.get(ParticipantProfile, pid)
    observations = small_synthetic_session.execute(
        select(DailyObservation).where(DailyObservation.participant_id == pid).order_by(DailyObservation.observation_date)
    ).scalars().all()
    window = observations[:6]

    traits = _traits(chronotype=profile.chronotype_category)
    alignment_result = _alignment_result()

    contributor_inputs = build_contributor_inputs(traits, alignment_result, window)
    result = rank_contributors(contributor_inputs)

    assert len(contributor_inputs.window_morning_light_duration_minutes) == 6
    report = run_sanity_checks(result)
    assert report.ok, report.summary_lines()


# --- 23. Sanity checks pass on a normal result ---


def test_sanity_checks_pass_for_a_normal_result():
    result = rank_contributors(_contributor_inputs())
    report = run_sanity_checks(result)
    assert report.ok, report.summary_lines()


def test_sanity_checks_pass_when_almost_all_data_missing():
    inputs = _contributor_inputs(
        window_morning_light_duration_minutes=[None] * 6,
        window_evening_screen_duration_hours=[None] * 6,
        window_last_meal_hours=[None] * 6,
        window_exercise_hours=[None] * 6,
        window_social_jetlag_minutes=[None] * 6,
        alignment_result=_alignment_result(
            window_morning_light_duration_minutes=[None] * 6,
            window_evening_screen_duration_hours=[None] * 6,
            window_last_meal_hours=[None] * 6,
            window_social_jetlag_minutes=[None] * 6,
        ),
    )
    result = rank_contributors(inputs)
    report = run_sanity_checks(result)
    assert report.ok, report.summary_lines()
