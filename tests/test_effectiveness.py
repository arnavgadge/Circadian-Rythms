"""Tests for the Phase 12 intervention feedback / effectiveness system."""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from app.effectiveness.compliance import (
    evaluate_compliance,
    evaluate_meal_timing_compliance,
    evaluate_morning_light_compliance,
    evaluate_screen_cutoff_compliance,
)
from app.effectiveness.config import DEFAULT_EFFECTIVENESS_CONFIG, MATCHED_OBSERVATIONAL, OBSERVATIONAL, REGRESSION_CONTROLLED_ESTIMATE
from app.effectiveness.confound import detect_confounds
from app.effectiveness.dispatcher import evaluate_intervention_effect
from app.effectiveness.outcomes import dlmo_change_minutes
from app.effectiveness.phase1 import DayRecord, evaluate_phase1_effect
from app.effectiveness.phase2 import evaluate_phase2_effect, find_matched_period
from app.effectiveness.phase3 import evaluate_phase3_effect
from app.effectiveness.windows import (
    INSUFFICIENT_BASELINE_HISTORY,
    INSUFFICIENT_INTERVENTION_HISTORY,
    InterventionEpisode,
    detect_episodes,
    select_baseline_window,
    select_intervention_window,
)
from app.synthetic.time_utils import normalize_hour

BASE_DATE = date(2026, 2, 1)


def _dates(start: date, n: int) -> list:
    return [start + timedelta(days=i) for i in range(n)]


def _full_signal_values(**overrides) -> dict:
    defaults = {"evening_screen": None, "morning_light": None, "meal_timing": None, "exercise": None, "social_jetlag": None}
    defaults.update(overrides)
    return defaults


# --- 1. Screen-cutoff compliance ---


def test_screen_cutoff_full_partial_low_compliance():
    full = evaluate_screen_cutoff_compliance(0.0, 23.75)  # 23:45, 15 min early
    partial = evaluate_screen_cutoff_compliance(0.0, 0.25)  # 00:15, 15 min late
    low = evaluate_screen_cutoff_compliance(0.0, 1.0)  # 01:00, 60 min late

    assert full.compliance_degree == pytest.approx(1.0)
    assert 0.4 < partial.compliance_degree < 0.8
    assert low.compliance_degree < partial.compliance_degree
    assert full.compliance_degree > partial.compliance_degree > low.compliance_degree


# --- 2. Circular compliance around midnight ---


def test_circular_compliance_never_treats_near_midnight_as_23_hours_apart():
    result = evaluate_screen_cutoff_compliance(0.0, 23.9167)  # 23:55, 5 min early
    assert result.compliance_degree == pytest.approx(1.0)
    assert abs(result.deviation) < 10.0  # minutes -- never ~23h50m


# --- 3. Morning-light compliance ---


def test_morning_light_compliance_full_when_met_and_decays_when_short():
    met = evaluate_morning_light_compliance(30.0, 35.0)
    short = evaluate_morning_light_compliance(30.0, 10.0)
    assert met.compliance_degree == pytest.approx(1.0)
    assert 0.0 < short.compliance_degree < 1.0


# --- 4. Meal compliance ---


def test_meal_timing_compliance_direction():
    early = evaluate_meal_timing_compliance(22.0, 21.5)  # ate earlier than target -> compliant
    late = evaluate_meal_timing_compliance(22.0, 23.0)  # ate later -> degraded
    assert early.compliance_degree == pytest.approx(1.0)
    assert late.compliance_degree < 1.0


# --- 5. Binary compliance threshold ---


def test_binary_threshold_matches_configured_default():
    config = DEFAULT_EFFECTIVENESS_CONFIG
    assert config.compliance_binary_threshold == pytest.approx(0.65)
    just_above = evaluate_screen_cutoff_compliance(0.0, normalize_hour(-(-math.log(0.66) * 30) / 60.0))
    # degree should cross the 0.65 boundary near a ~12.5 minute deviation
    boundary_result = evaluate_screen_cutoff_compliance(0.0, 12.0 / 60.0)
    assert boundary_result.compliance_binary == (boundary_result.compliance_degree >= 0.65)


# --- 6. Missing vs non-compliant distinction ---


def test_missing_observation_is_not_treated_as_noncompliant():
    missing = evaluate_compliance("evening_screen", 0.0, None)
    noncompliant = evaluate_compliance("evening_screen", 0.0, 2.0)  # 2 hours late -> observed, poor compliance

    assert missing.available is False
    assert missing.compliance_binary is None  # not False -- unknown, not failed
    assert noncompliant.available is True
    assert noncompliant.compliance_binary is False


# --- 7. Baseline window selection ---


def test_baseline_window_selected_when_fully_present():
    episode_start = BASE_DATE + timedelta(days=10)
    available = set(_dates(BASE_DATE + timedelta(days=3), 7))  # exactly the 7 days before start
    period = select_baseline_window(episode_start, available)
    assert period is not None
    assert period.start_date == BASE_DATE + timedelta(days=3)
    assert period.end_date == episode_start - timedelta(days=1)
    assert len(period.observed_dates) == 7


# --- 8. Intervention window selection ---


def test_intervention_window_selected_for_full_episode():
    episode = InterventionEpisode(1, BASE_DATE, BASE_DATE + timedelta(days=6), tuple(_dates(BASE_DATE, 7)))
    available = set(episode.log_dates)
    period = select_intervention_window(episode, available)
    assert period is not None
    assert len(period.observed_dates) == 7


# --- 9. Insufficient baseline history ---


def test_insufficient_baseline_history_returns_none():
    episode_start = BASE_DATE + timedelta(days=10)
    available = set(_dates(episode_start - timedelta(days=2), 2))  # only 2 of 7 baseline days
    assert select_baseline_window(episode_start, available) is None


# --- 10. Insufficient intervention history ---


def test_insufficient_intervention_history_returns_none():
    episode = InterventionEpisode(1, BASE_DATE, BASE_DATE + timedelta(days=1), tuple(_dates(BASE_DATE, 2)))
    available = {BASE_DATE}  # only 1 of 2 days observed
    assert select_intervention_window(episode, available) is None


# --- 11 & 12 & 13. Before/after DLMO + alignment + circular DLMO change ---


def _phase1_records(dlmo_baseline: float, dlmo_recent: float, compliant: bool = True) -> tuple:
    episode_start = BASE_DATE + timedelta(days=7)
    records = {}
    for i, d in enumerate(_dates(BASE_DATE, 7)):
        records[d] = DayRecord(d, dlmo_hour=dlmo_baseline, alignment_score=60.0, signal_values=_full_signal_values())
    for i, d in enumerate(_dates(episode_start, 7)):
        records[d] = DayRecord(
            d, dlmo_hour=dlmo_recent, alignment_score=74.0,
            signal_values=_full_signal_values(evening_screen=0.0),
            compliance_degree=1.0 if compliant else 0.1,
        )
    episode = InterventionEpisode(1, episode_start, episode_start + timedelta(days=6), tuple(_dates(episode_start, 7)))
    return episode, records


def test_phase1_before_after_dlmo_and_alignment():
    episode, records = _phase1_records(dlmo_baseline=0.1667, dlmo_recent=23.9)  # 00:10 -> 23:54, a 16 min advance
    result = evaluate_phase1_effect(1, 1, "evening_screen", episode, records)

    assert result.sufficient_data
    assert result.baseline_dlmo == pytest.approx(0.1667, abs=1e-3)
    assert result.recent_dlmo == pytest.approx(23.9, abs=1e-3)
    assert result.baseline_alignment == pytest.approx(60.0)
    assert result.recent_alignment == pytest.approx(74.0)
    assert result.alignment_change == pytest.approx(14.0)
    assert result.interpretation == OBSERVATIONAL
    assert result.measurement_phase == 1


def test_circular_dlmo_change_handles_midnight_wraparound():
    # 23:55 -> 00:10 must be +15 minutes, not -23h45m.
    change = dlmo_change_minutes(23.9167, 0.1667)
    assert change == pytest.approx(15.0, abs=0.1)


# --- 14. Compliance rate ---


def test_compliance_rate_counts_only_observed_days():
    episode_start = BASE_DATE + timedelta(days=7)
    episode = InterventionEpisode(1, episode_start, episode_start + timedelta(days=6), tuple(_dates(episode_start, 7)))
    records = {d: DayRecord(d, dlmo_hour=21.0, alignment_score=60.0, signal_values=_full_signal_values()) for d in _dates(BASE_DATE, 7)}
    degrees = [1.0, 1.0, 0.1, None, 1.0, 0.1, None]  # 2 missing, 5 observed, 3 compliant
    for d, deg in zip(_dates(episode_start, 7), degrees):
        records[d] = DayRecord(d, dlmo_hour=21.0, alignment_score=70.0, signal_values=_full_signal_values(), compliance_degree=deg)

    result = evaluate_phase1_effect(1, 1, "evening_screen", episode, records)
    assert result.observed_days == 5
    assert result.compliance_days == 3
    assert result.compliance_rate == pytest.approx(3 / 5)


# --- 15. Confound detection ---


def test_confound_flagged_when_other_signal_changes_substantially():
    deltas = {"evening_screen": -20.0, "morning_light": 25.0, "meal_timing": 2.0, "exercise": 1.0, "social_jetlag": 0.0}
    report = detect_confounds("evening_screen", deltas)
    assert report.confound_flag is True
    assert "morning_light" in report.changed_signals
    assert "evening_screen" not in report.changed_signals  # target itself is excluded


def test_no_confound_when_other_signals_stable():
    deltas = {"evening_screen": -20.0, "morning_light": 2.0, "meal_timing": 1.0, "exercise": 1.0, "social_jetlag": 0.0}
    report = detect_confounds("evening_screen", deltas)
    assert report.confound_flag is False


# --- 16 & 17 & 18. Matched-period selection / target exclusion / match quality ---


def _phase2_history() -> dict:
    history = {}
    # A "quiet" identical-covariate week far in the past (perfect match candidate).
    for d in _dates(BASE_DATE, 7):
        history[d] = DayRecord(
            d, dlmo_hour=21.0, alignment_score=55.0,
            signal_values=_full_signal_values(morning_light=20.0, meal_timing=22.0, exercise=18.0, evening_screen=1.5),
        )
    # A dissimilar middle week.
    for d in _dates(BASE_DATE + timedelta(days=10), 7):
        history[d] = DayRecord(
            d, dlmo_hour=21.2, alignment_score=58.0,
            signal_values=_full_signal_values(morning_light=60.0, meal_timing=19.0, exercise=12.0, evening_screen=1.6),
        )
    # The intervention week: same non-target covariates as the first
    # week, but the target (evening_screen) is different.
    intervention_start = BASE_DATE + timedelta(days=30)
    for d in _dates(intervention_start, 7):
        history[d] = DayRecord(
            d, dlmo_hour=20.7, alignment_score=70.0,
            signal_values=_full_signal_values(morning_light=20.0, meal_timing=22.0, exercise=18.0, evening_screen=0.0),
            compliance_degree=1.0,
        )
    return history, intervention_start


def test_matched_period_prefers_similar_non_target_covariates():
    history, intervention_start = _phase2_history()
    episode = InterventionEpisode(1, intervention_start, intervention_start + timedelta(days=6), tuple(_dates(intervention_start, 7)))
    intervention_period = select_intervention_window(episode, set(episode.log_dates))

    match = find_matched_period(history, intervention_period, "evening_screen")
    assert match is not None
    assert match.matched_period_start == BASE_DATE  # the identical-covariate week, not the dissimilar one
    assert "evening_screen" not in match.variables_matched
    assert match.target_variable_excluded == "evening_screen"


def test_match_quality_invalid_when_no_similar_period_exists():
    history, intervention_start = _phase2_history()
    del history[BASE_DATE]  # remove the identical-covariate candidate, keep only the dissimilar week
    for i in range(1, 7):
        del history[BASE_DATE + timedelta(days=i)]

    episode = InterventionEpisode(1, intervention_start, intervention_start + timedelta(days=6), tuple(_dates(intervention_start, 7)))
    intervention_period = select_intervention_window(episode, set(episode.log_dates))

    match = find_matched_period(history, intervention_period, "evening_screen")
    assert match is not None
    assert match.match_valid is False  # only the dissimilar week remains as a candidate


def test_evaluate_phase2_effect_end_to_end():
    from app.effectiveness.config import EffectivenessConfig

    history, intervention_start = _phase2_history()
    episode = InterventionEpisode(1, intervention_start, intervention_start + timedelta(days=6), tuple(_dates(intervention_start, 7)))
    intervention_period = select_intervention_window(episode, set(episode.log_dates))

    # The hand-built fixture only populates 3 discrete weeks (21 days)
    # rather than a continuous calendar history; min_history_days_for_phase2
    # counts populated days, so it is relaxed here to match the fixture's
    # own scale rather than padding it with irrelevant filler days.
    config = EffectivenessConfig(min_history_days_for_phase2=21)

    result = evaluate_phase2_effect(1, 1, "evening_screen", history, intervention_period, config)
    assert result.sufficient_data
    assert result.interpretation == MATCHED_OBSERVATIONAL
    assert result.measurement_phase == 2
    assert result.mean_dlmo_difference is not None


# --- 19. Matched slope calculation ---


def test_dlmo_slope_recovers_known_linear_drift():
    from app.effectiveness.phase2 import _dlmo_slope_per_day

    # A steady 5-minute-per-day advance, wrapping through midnight.
    hours = [normalize_hour(22.0 - i * (5.0 / 60.0)) for i in range(10)]
    slope = _dlmo_slope_per_day(hours)
    assert slope == pytest.approx(-5.0, abs=0.5)


# --- 20 & 22. Phase-3 regression setup / confidence interval ---


def _phase3_known_ground_truth(n: int = 30, true_effect: float = -10.0):
    """A controlled synthetic fixture with a known, exact (noise-free)
    compliance -> DLMO-change relationship, so the regression's
    recovered coefficient can be checked against ground truth."""

    records = {}
    dlmo = 21.0
    base_date = BASE_DATE
    records[base_date] = DayRecord(base_date, dlmo_hour=dlmo, alignment_score=60.0, signal_values=_full_signal_values(
        morning_light=50.0, meal_timing=22.0, exercise=18.0,
    ))
    compliance_series = []
    for i in range(1, n):
        d = base_date + timedelta(days=i)
        compliance = (i % 10) / 10.0
        compliance_series.append(compliance)
        change_minutes = true_effect * compliance
        dlmo = normalize_hour(dlmo + change_minutes / 60.0)
        records[d] = DayRecord(
            d, dlmo_hour=dlmo, alignment_score=60.0 + i * 0.1,
            signal_values=_full_signal_values(
                morning_light=50.0 + 5 * math.sin(i), meal_timing=22.0 + 0.1 * math.cos(i), exercise=18.0 + 0.1 * math.sin(i * 0.5),
            ),
            compliance_degree=compliance,
        )
    return records


def test_phase3_regression_recovers_known_synthetic_effect():
    records = _phase3_known_ground_truth(n=30, true_effect=-10.0)
    result = evaluate_phase3_effect(1, 1, records, baseline_dlmo_reference=21.0)

    assert result.sufficient_data
    assert result.interpretation == REGRESSION_CONTROLLED_ESTIMATE
    assert result.effect_mins_per_compliance_unit == pytest.approx(-10.0, abs=0.5)
    assert result.r_squared > 0.98
    assert result.confidence_interval_lower <= result.effect_mins_per_compliance_unit <= result.confidence_interval_upper
    assert result.confidence_interval_upper - result.confidence_interval_lower < 5.0  # tight CI given zero noise


# --- 21. Insufficient regression data ---


def test_phase3_insufficient_data_for_small_sample():
    records = _phase3_known_ground_truth(n=10, true_effect=-10.0)  # well under min_regression_observations
    result = evaluate_phase3_effect(1, 1, records, baseline_dlmo_reference=21.0)
    assert not result.sufficient_data
    assert result.insufficiency_reason == "insufficient_data"
    assert result.effect_mins_per_compliance_unit is None


# --- 23. Intervention-specific effect separation ---


def test_different_interventions_never_share_an_estimate():
    records_a = _phase3_known_ground_truth(n=30, true_effect=-10.0)
    records_b = _phase3_known_ground_truth(n=30, true_effect=+6.0)

    result_a = evaluate_phase3_effect(101, 1, records_a, baseline_dlmo_reference=21.0)
    result_b = evaluate_phase3_effect(202, 1, records_b, baseline_dlmo_reference=21.0)

    assert result_a.effect_mins_per_compliance_unit == pytest.approx(-10.0, abs=0.5)
    assert result_b.effect_mins_per_compliance_unit == pytest.approx(6.0, abs=0.5)
    assert result_a.intervention_id != result_b.intervention_id


# --- 25. Phase dispatcher ---


def test_dispatcher_picks_highest_valid_phase_phase1_only():
    episode, records = _phase1_records(dlmo_baseline=21.0, dlmo_recent=20.5)
    result = evaluate_intervention_effect(1, 1, "evening_screen", episode, records)
    assert result.chosen_phase == 1
    assert result.phase2 is None or not result.phase2.sufficient_data
    assert result.phase3 is None or not result.phase3.sufficient_data


def test_dispatcher_never_jumps_to_phase3_with_insufficient_history():
    episode, records = _phase1_records(dlmo_baseline=21.0, dlmo_recent=20.5)
    result = evaluate_intervention_effect(1, 1, "evening_screen", episode, records)
    assert result.chosen_phase != 3


def test_dispatcher_returns_none_when_even_phase1_is_insufficient():
    episode = InterventionEpisode(1, BASE_DATE, BASE_DATE, (BASE_DATE,))
    records = {BASE_DATE: DayRecord(BASE_DATE, dlmo_hour=21.0, alignment_score=60.0, signal_values=_full_signal_values())}
    result = evaluate_intervention_effect(1, 1, "evening_screen", episode, records)
    assert result.chosen_phase is None
    assert not result.phase1.sufficient_data
    assert result.phase1.insufficiency_reason == INSUFFICIENT_BASELINE_HISTORY


# --- 26. Multiple simultaneous interventions (episode detection identity) ---


def test_episode_detection_splits_on_recommendation_change_and_gaps():
    class _Row:
        def __init__(self, log_date, recommendation_id):
            self.log_date = log_date
            self.recommendation_id = recommendation_id

    rows = [
        _Row(BASE_DATE, 1), _Row(BASE_DATE + timedelta(days=1), 1),
        _Row(BASE_DATE + timedelta(days=2), 2),  # switched intervention
        _Row(BASE_DATE + timedelta(days=10), 2),  # same intervention, but a gap -> new episode
    ]
    episodes = detect_episodes(rows)
    assert len(episodes) == 3
    assert episodes[0].recommendation_id == 1 and len(episodes[0].log_dates) == 2
    assert episodes[1].recommendation_id == 2 and episodes[1].start_date == BASE_DATE + timedelta(days=2)
    assert episodes[2].recommendation_id == 2 and episodes[2].start_date == BASE_DATE + timedelta(days=10)


# --- 27. Deterministic repeated evaluation ---


def test_repeated_evaluation_is_deterministic():
    episode, records = _phase1_records(dlmo_baseline=21.0, dlmo_recent=20.5)
    result_a = evaluate_intervention_effect(1, 1, "evening_screen", episode, records)
    result_b = evaluate_intervention_effect(1, 1, "evening_screen", episode, records)
    assert result_a.phase1.effect_estimate == pytest.approx(result_b.phase1.effect_estimate)
    assert result_a.chosen_phase == result_b.chosen_phase
