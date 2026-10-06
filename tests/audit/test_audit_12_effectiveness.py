"""AUDIT 12 -- Intervention effectiveness adversarial checks.

Unit-level (DayRecord/Period construction, no DB needed) checks for:
missing observations excluded from the compliance denominator (not
counted as failure), baseline/intervention window separation, confound
detection on a constructed confounded scenario, and the three
measurement-phase interpretation labels' semantics.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.effectiveness.compliance import evaluate_screen_cutoff_compliance
from app.effectiveness.config import (
    DEFAULT_EFFECTIVENESS_CONFIG,
    MATCHED_OBSERVATIONAL,
    OBSERVATIONAL,
    PHASE_INTERPRETATION,
    REGRESSION_CONTROLLED_ESTIMATE,
)
from app.effectiveness.confound import detect_confounds
from app.effectiveness.outcomes import dlmo_change_minutes
from app.effectiveness.phase1 import DayRecord, evaluate_phase1_effect
from app.effectiveness.windows import InterventionEpisode, select_baseline_window, select_intervention_window

BASE_DATE = date(2026, 1, 1)


# --- Missing observation is NOT non-compliance ---


def test_missing_day_excluded_from_compliance_denominator_not_treated_as_failure():
    """A day with no logged compliance_degree (actual_value unresolved)
    must be excluded from the compliance rate's denominator entirely --
    never silently counted as a failed/non-compliant day, which would
    unfairly punish a participant simply for a missing observation."""

    episode = InterventionEpisode(
        recommendation_id=1, start_date=BASE_DATE, end_date=BASE_DATE + timedelta(days=6),
        log_dates=tuple(BASE_DATE + timedelta(days=i) for i in range(7)),
    )
    records = {}
    # 4 fully-compliant days, 1 non-compliant day, 2 days with NO
    # compliance_degree at all (missing observation, e.g. participant
    # didn't log / DLMO unavailable that day).
    compliance_by_day = [1.0, 1.0, 1.0, 1.0, 0.0, None, None]
    for i, comp in enumerate(compliance_by_day):
        d = BASE_DATE + timedelta(days=i)
        records[d] = DayRecord(date=d, dlmo_hour=21.0, alignment_score=70.0, signal_values={}, compliance_degree=comp)
    for i in range(1, 8):  # baseline window before episode
        d = BASE_DATE - timedelta(days=i)
        records[d] = DayRecord(date=d, dlmo_hour=21.0, alignment_score=70.0, signal_values={})

    result = evaluate_phase1_effect(1, 1, "evening_screen", episode, records)
    assert result.sufficient_data
    # Denominator must be 5 (the resolved days), not 7 (all episode days).
    assert result.observed_days == 5
    assert result.compliance_days == 4
    assert result.compliance_rate == pytest.approx(4 / 5)


def test_compliance_evaluator_returns_unavailable_not_a_failure_for_missing_actual():
    """The compliance evaluator itself: a None actual_value (missing
    observation) must resolve to available=False / compliance_binary=None
    -- never compliance_degree=0.0 (which would read as an outright
    failure rather than absent data)."""

    result = evaluate_screen_cutoff_compliance(target_hour=22.0, actual_hour=None)
    assert result.available is False
    assert result.compliance_degree is None
    assert result.compliance_binary is None


# --- Baseline never includes intervention-period data ---


def test_baseline_window_never_touches_or_crosses_episode_start():
    episode_start = BASE_DATE + timedelta(days=30)
    available_dates = {episode_start + timedelta(days=i) for i in range(-40, 10)}  # includes plenty of future dates too
    period = select_baseline_window(episode_start, available_dates, DEFAULT_EFFECTIVENESS_CONFIG)
    assert period is not None
    assert period.end_date < episode_start
    for d in period.observed_dates:
        assert d < episode_start


def test_intervention_window_never_reaches_beyond_the_episodes_own_dates():
    """The intervention-period window is built purely from the episode's
    own log_dates -- it structurally cannot include a date the episode
    itself doesn't contain (which would mean pulling in data the
    intervention wasn't even logged for, i.e. from a different/later
    episode or the future)."""

    log_dates = tuple(BASE_DATE + timedelta(days=i) for i in range(10))
    episode = InterventionEpisode(1, log_dates[0], log_dates[-1], log_dates)
    available_dates = set(log_dates) | {log_dates[-1] + timedelta(days=i) for i in range(1, 30)}  # future dates exist elsewhere
    period = select_intervention_window(episode, available_dates, DEFAULT_EFFECTIVENESS_CONFIG)
    assert period is not None
    assert all(d in log_dates for d in period.observed_dates)
    assert period.end_date <= log_dates[-1]


# --- Confound detection on a constructed confounded scenario ---


def test_confound_detected_when_a_non_target_signal_also_shifted_substantially():
    """Adversarial scenario: the intervention targets evening_screen,
    but morning_light ALSO shifted by a large amount over the same
    period (e.g. a coincidental seasonal daylight change) -- the
    confound flag must catch this rather than silently attributing the
    whole DLMO change to the screen intervention."""

    deltas = {
        "evening_screen": -10.0,  # the target signal itself -- excluded from confound scan
        "morning_light": 40.0,    # exceeds morning_light's 15.0-minute threshold
        "meal_timing": 2.0,       # well within its 20.0-minute threshold
        "exercise": None,         # missing -- must not crash or falsely flag
        "social_jetlag": 5.0,
    }
    report = detect_confounds("evening_screen", deltas, DEFAULT_EFFECTIVENESS_CONFIG)
    assert report.confound_flag is True
    assert "morning_light" in report.changed_signals
    assert "evening_screen" not in report.changed_signals  # never flags the target itself
    assert "meal_timing" not in report.changed_signals
    assert "exercise" not in report.changed_signals


def test_no_confound_flag_when_only_the_target_signal_changed():
    deltas = {"evening_screen": -25.0, "morning_light": 2.0, "meal_timing": 1.0, "exercise": 3.0, "social_jetlag": 1.0}
    report = detect_confounds("evening_screen", deltas, DEFAULT_EFFECTIVENESS_CONFIG)
    assert report.confound_flag is False
    assert report.changed_signals == {}


def test_misleading_naive_comparison_scenario_still_surfaces_confound_caveat():
    """A naive before/after comparison would look like a clean win: DLMO
    improved by 20 minutes exactly when the screen intervention started.
    But morning_light ALSO happened to shift a lot in that same window
    (e.g. an unrelated seasonal change) -- the system's real Phase 1
    output must carry confound_flag=True rather than silently reporting
    the DLMO change as a clean intervention effect."""

    episode = InterventionEpisode(
        recommendation_id=1, start_date=BASE_DATE, end_date=BASE_DATE + timedelta(days=6),
        log_dates=tuple(BASE_DATE + timedelta(days=i) for i in range(7)),
    )
    records = {}
    for i in range(7):
        d = BASE_DATE + timedelta(days=i)
        records[d] = DayRecord(
            date=d, dlmo_hour=20.5, alignment_score=75.0,
            signal_values={"evening_screen": 21.5, "morning_light": 90.0, "meal_timing": 19.5, "exercise": 18.0, "social_jetlag": 10.0},
            compliance_degree=1.0,
        )
    for i in range(1, 8):
        d = BASE_DATE - timedelta(days=i)
        records[d] = DayRecord(
            date=d, dlmo_hour=21.0, alignment_score=65.0,
            # A confound: morning_light was much LOWER in baseline (seasonal
            # daylight change coincides with the intervention start), well
            # beyond its 15-min confound threshold, alongside the targeted
            # evening_screen change.
            signal_values={"evening_screen": 23.5, "morning_light": 20.0, "meal_timing": 19.7, "exercise": 18.2, "social_jetlag": 12.0},
        )

    result = evaluate_phase1_effect(1, 1, "evening_screen", episode, records)
    assert result.sufficient_data
    assert result.dlmo_change_minutes is not None and result.dlmo_change_minutes < 0  # looks like a clean "win"
    assert result.confound_flag is True  # ...but the system flags it as confounded, not a clean causal claim
    assert result.interpretation == OBSERVATIONAL  # never claims more than observational at Phase 1


# --- Measurement-phase labels match documented semantics ---


def test_dlmo_change_across_midnight_uses_circular_not_naive_difference():
    """Baseline DLMO 23:50 (23.833h), recent DLMO 00:10 (0.167h): a naive
    ``recent - baseline`` gives -23.67h (a nonsensical ~23h "advance");
    the correct circular reading is a +20 minute delay -- re-verified
    specifically inside app.effectiveness.outcomes, not just trusted
    from a general audit-6 sweep."""

    change = dlmo_change_minutes(baseline_hour=23.833333, recent_hour=0.166667)
    assert change == pytest.approx(20.0, abs=0.1)
    assert change > 0  # a delay, not a nonsensical -23h "advance"


def test_measurement_phase_semantics_match_docs_and_frontend_mapping():
    """Phase 1 = observational, Phase 2 = matched observational, Phase 3
    = regression-controlled estimate -- cross-checked against the
    actual PHASE_INTERPRETATION dict the backend uses (the same
    semantics frontend/src/components/InterventionProgress.tsx's
    PHASE_LABELS assumes: 1='Observed change', 2='...similar previous
    period', 3='Estimated personal effect')."""

    assert PHASE_INTERPRETATION[1] == OBSERVATIONAL
    assert PHASE_INTERPRETATION[2] == MATCHED_OBSERVATIONAL
    assert PHASE_INTERPRETATION[3] == REGRESSION_CONTROLLED_ESTIMATE
