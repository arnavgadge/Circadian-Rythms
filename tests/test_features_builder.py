"""Tests for the main feature builder: leakage prevention, MEQ/MSFsc,
missing-data handling, and determinism -- against a small real Phase 3
synthetic dataset (5 participants x 30 days).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.database.models import DailyObservation, Participant
from app.features.builder import build_features
from app.features.feature_manifest import TOTAL_FEATURE_COUNT

FIRST_TARGET_DATE = date(2026, 1, 11)  # start_date 2026-01-05 + 6 days


def _first_participant_id(session) -> int:
    return session.execute(select(Participant.id).order_by(Participant.id)).scalars().first()


def test_exact_68_features_returned(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    assert len(fv.features) == TOTAL_FEATURE_COUNT
    assert len(fv.feature_names) == TOTAL_FEATURE_COUNT


def test_window_covers_exactly_the_six_preceding_days(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    assert fv.window_start == date(2026, 1, 5)
    assert fv.window_end == date(2026, 1, 10)
    assert fv.window_end == FIRST_TARGET_DATE - timedelta(days=1)
    assert fv.window_start == FIRST_TARGET_DATE - timedelta(days=6)


def test_target_day_is_never_included_in_the_window(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    assert max(fv.window_start, fv.window_end) == fv.target_date - timedelta(days=1)


def test_future_day_is_never_included(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    target = date(2026, 1, 20)
    fv = build_features(pid, target, small_synthetic_session)
    assert fv.window_end < target
    for offset in range(1, 10):
        future_date = target + timedelta(days=offset)
        assert future_date not in (fv.window_start, fv.window_end)


def test_meq_normalized_is_computed_correctly(small_synthetic_session):
    from app.database.models import ParticipantProfile

    pid = _first_participant_id(small_synthetic_session)
    profile = small_synthetic_session.get(ParticipantProfile, pid)
    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)

    expected = (profile.meq_score - 16) / 70
    assert fv.features["meq_normalized"] == pytest.approx(expected)
    assert 0.0 <= fv.features["meq_normalized"] <= 1.0


def test_msfsc_features_are_valid_circular_values(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    assert -1.0 <= fv.features["msfsc_sin"] <= 1.0
    assert -1.0 <= fv.features["msfsc_cos"] <= 1.0


def test_meq_msfsc_divergence_is_a_bounded_hour_difference(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    # A circular difference in hours is always within (-12, 12].
    assert -12.0 < fv.features["meq_msfsc_divergence"] <= 12.0


def test_deterministic_repeated_generation_is_identical(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    fv1 = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    fv2 = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    assert fv1.features == fv2.features
    assert fv1.feature_values == fv2.feature_values


def test_complete_data_has_full_completeness(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    assert fv.completeness == pytest.approx(1.0)
    assert fv.missing_features == []
    assert fv.imputed_features == []


def test_missing_evening_screen_end_triggers_population_default_imputation(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)

    # Null out evening_screen_end_time for the ENTIRE window (all 6 days)
    # and remove any earlier history too, forcing the population-default
    # fallback path (no window data, no personal history).
    small_synthetic_session.execute(
        DailyObservation.__table__.update()
        .where(DailyObservation.participant_id == pid)
        .values(evening_screen_end_time=None)
    )
    small_synthetic_session.commit()

    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)

    assert "screen_end_day_1_sin" in fv.missing_features
    assert "screen_end_day_1_cos" in fv.missing_features
    assert fv.imputation_methods["screen_end_day_1_sin"] == "population_default"
    assert fv.completeness < 1.0
    assert fv.tier_missing_counts["tier_1"] > 0


def test_missing_single_day_falls_back_to_personal_history(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)

    # Null out caffeine_amount_mg only within the window (days 1-6), but
    # leave earlier history (before window_start) intact so the
    # personal-history fallback has something to use.
    window_start = FIRST_TARGET_DATE - timedelta(days=6)
    window_end = FIRST_TARGET_DATE - timedelta(days=1)
    small_synthetic_session.execute(
        DailyObservation.__table__.update()
        .where(
            DailyObservation.participant_id == pid,
            DailyObservation.observation_date >= window_start,
            DailyObservation.observation_date <= window_end,
        )
        .values(caffeine_amount_mg=None)
    )
    small_synthetic_session.commit()

    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)

    assert "caffeine_amount_mean_mg" in fv.missing_features
    # window_start (2026-01-05) is the participant's very first day, so
    # there IS no personal history before it -> must fall to population default.
    assert fv.imputation_methods["caffeine_amount_mean_mg"] == "population_default"


def test_missing_data_with_prior_history_uses_personal_history_not_default(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    target = date(2026, 1, 20)  # window 2026-01-14..2026-01-19, prior history exists
    window_start = target - timedelta(days=6)
    window_end = target - timedelta(days=1)

    small_synthetic_session.execute(
        DailyObservation.__table__.update()
        .where(
            DailyObservation.participant_id == pid,
            DailyObservation.observation_date >= window_start,
            DailyObservation.observation_date <= window_end,
        )
        .values(caffeine_amount_mg=None)
    )
    small_synthetic_session.commit()

    fv = build_features(pid, target, small_synthetic_session)

    assert "caffeine_amount_mean_mg" in fv.missing_features
    assert fv.imputation_methods["caffeine_amount_mean_mg"] == "personal_history"


def test_tier_missing_counts_reflect_signal_tiers(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    window_start = FIRST_TARGET_DATE - timedelta(days=6)
    window_end = FIRST_TARGET_DATE - timedelta(days=1)

    # Morning light is Tier 1.
    small_synthetic_session.execute(
        DailyObservation.__table__.update()
        .where(
            DailyObservation.participant_id == pid,
            DailyObservation.observation_date >= window_start,
            DailyObservation.observation_date <= window_end,
        )
        .values(morning_light_start_time=None, morning_light_duration_minutes=None)
    )
    small_synthetic_session.commit()

    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    assert fv.tier_missing_counts["tier_1"] > 0
