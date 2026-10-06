"""Tests for the top-level compute_alignment() orchestration."""

from __future__ import annotations

import pytest

from app.alignment.config import AlignmentConfig, DEFAULT_ALIGNMENT_CONFIG
from app.alignment.engine import compute_alignment
from app.alignment.inputs import AlignmentInputs
from app.alignment.sanity import run_sanity_checks, run_structural_checks


def _full_inputs(**overrides) -> AlignmentInputs:
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
    return AlignmentInputs(**defaults)


# --- 11. Final 60/40 weighted sum ---

def test_final_score_is_60_40_weighted_sum():
    result = compute_alignment(_full_inputs())
    expected = 0.60 * result.phase_score + 0.40 * result.behavioral_score
    assert result.final_score == pytest.approx(expected, abs=1e-6)


# --- 12. Component weight validation ---

def test_default_config_weights_are_valid():
    DEFAULT_ALIGNMENT_CONFIG.validate()  # must not raise


def test_invalid_top_level_weights_raise():
    bad_config = AlignmentConfig(phase_alignment_weight=0.5, behavioral_alignment_weight=0.4)
    with pytest.raises(ValueError):
        bad_config.validate()


def test_invalid_behavioral_weights_raise():
    bad_config = AlignmentConfig(sleep_consistency_weight=0.3)  # now sums to 1.05
    with pytest.raises(ValueError):
        bad_config.validate()


# --- 13, 14. Missing-component handling / imputation metadata ---

def test_missing_current_day_sleep_onset_is_imputed_and_tracked():
    result = compute_alignment(_full_inputs(most_recent_sleep_onset_hour=None))
    assert "phase" in result.imputed_components
    assert result.data_completeness < 1.0


def test_fully_missing_component_is_tracked_as_imputed():
    result = compute_alignment(_full_inputs(window_morning_light_duration_minutes=[None] * 6))
    assert "morning_light" in result.imputed_components


def test_complete_data_has_full_completeness_and_no_imputation():
    result = compute_alignment(_full_inputs())
    assert result.data_completeness == pytest.approx(1.0)
    assert result.imputed_components == []


def test_data_completeness_reflects_fraction_of_six_slots():
    result = compute_alignment(
        _full_inputs(
            window_morning_light_duration_minutes=[None] * 6,
            window_evening_screen_duration_hours=[None] * 6,
        )
    )
    assert result.data_completeness == pytest.approx(4 / 6, abs=1e-6)


# --- 15. Score bounds ---

def test_all_scores_within_bounds_for_extreme_input():
    result = compute_alignment(
        _full_inputs(
            fused_dlmo_hour=0.0,
            most_recent_sleep_onset_hour=12.0,
            window_sleep_onset_hours=[0.0, 12.0, 6.0, 18.0, 3.0, 9.0],
            window_evening_screen_duration_hours=[8.0] * 6,
            window_social_jetlag_minutes=[600.0] * 6,
        )
    )
    assert 0.0 <= result.final_score <= 100.0
    assert 0.0 <= result.phase_score <= 100.0
    assert 0.0 <= result.behavioral_score <= 100.0
    for component in result.behavioral_components.values():
        assert 0.0 <= component.score <= 100.0


# --- 16. No MEQ influence ---

def test_no_meq_field_anywhere_in_alignment_inputs_or_result():
    inputs = _full_inputs()
    result = compute_alignment(inputs)
    assert not hasattr(inputs, "meq_score")
    assert not hasattr(result, "meq_score")
    for component in result.behavioral_components.values():
        assert "meq" not in component.name.lower()


def test_structural_sanity_confirms_no_meq_influence():
    report = run_structural_checks()
    check = next(c for c in report.checks if c.name == "no_meq_influence")
    assert check.passed


# --- 17. Time-horizon correctness ---

def test_phase_alignment_uses_most_recent_day_not_window_average():
    # If the most recent day differs sharply from the window average,
    # phase alignment must reflect the *most recent day*, not the mean.
    result = compute_alignment(
        _full_inputs(most_recent_sleep_onset_hour=3.0, window_sleep_onset_hours=[23.5] * 6)
    )
    assert result.actual_sleep_onset_hour == pytest.approx(3.0)


def test_behavioral_alignment_uses_window_not_single_anomalous_day():
    # A single anomalous day embedded in an otherwise-consistent window
    # should not collapse the sleep-consistency score to near zero.
    onsets = [23.5, 23.4, 23.6, 23.5, 4.0, 23.5]  # one wild outlier
    from app.alignment.behavioral_components import compute_sleep_consistency_score

    result = compute_sleep_consistency_score(onsets)
    assert result.score > 0.0  # degraded, but not using only the anomalous day


# --- 18. Invalid input handling ---

def test_handles_all_none_window_gracefully():
    result = compute_alignment(
        _full_inputs(
            most_recent_sleep_onset_hour=None,
            window_sleep_onset_hours=[None] * 6,
            window_morning_light_duration_minutes=[None] * 6,
            window_evening_screen_duration_hours=[None] * 6,
            window_last_meal_hours=[None] * 6,
            window_social_jetlag_minutes=[None] * 6,
        )
    )
    assert 0.0 <= result.final_score <= 100.0
    assert result.data_completeness == pytest.approx(0.0)
    assert len(result.imputed_components) == 6


def test_handles_short_window_gracefully():
    result = compute_alignment(
        _full_inputs(
            window_sleep_onset_hours=[23.5, 23.6],
            window_morning_light_duration_minutes=[30.0],
            window_evening_screen_duration_hours=[],
            window_last_meal_hours=[19.0],
            window_social_jetlag_minutes=[],
        )
    )
    assert 0.0 <= result.final_score <= 100.0


# --- 19. Deterministic computation ---

def test_compute_alignment_is_deterministic():
    inputs = _full_inputs()
    result_a = compute_alignment(inputs)
    result_b = compute_alignment(inputs)
    assert result_a.final_score == pytest.approx(result_b.final_score, abs=1e-12)
    assert result_a.phase_score == pytest.approx(result_b.phase_score, abs=1e-12)


# --- 20. End-to-end alignment on a fixture participant ---

def test_end_to_end_healthy_routine_scores_well():
    result = compute_alignment(_full_inputs())
    assert result.final_score > 70.0  # a consistent, early, low-screen routine should score well


def test_end_to_end_chaotic_routine_scores_poorly():
    result = compute_alignment(
        _full_inputs(
            most_recent_sleep_onset_hour=3.0,
            window_sleep_onset_hours=[20.0, 2.0, 23.0, 1.0, 21.0, 3.0],
            window_evening_screen_duration_hours=[4.5] * 6,
            window_last_meal_hours=[23.5] * 6,
            window_social_jetlag_minutes=[200.0, None, None, None, None, None],
        )
    )
    assert result.final_score < 50.0


def test_sanity_checks_pass_for_a_normal_result():
    result = compute_alignment(_full_inputs())
    report = run_sanity_checks(result)
    assert report.ok, report.summary_lines()
