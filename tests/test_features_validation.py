"""Tests for the 15 automated feature sanity checks."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.database.models import Participant
from app.features.builder import build_features
from app.features.validation import validate_feature_vector

FIRST_TARGET_DATE = date(2026, 1, 11)


def _first_participant_id(session) -> int:
    return session.execute(select(Participant.id).order_by(Participant.id)).scalars().first()


def test_valid_vector_passes_every_check(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    report = validate_feature_vector(fv)
    assert report.ok, report.summary_lines()
    assert len(report.checks) == 15


def test_detects_out_of_bounds_circular_value(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    fv.features["msfsc_sin"] = 1.5  # break it
    report = validate_feature_vector(fv)
    check = next(c for c in report.checks if c.name == "circular_values_bounded")
    assert not check.passed


def test_detects_negative_duration(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    fv.features["sleep_duration_mean_hours"] = -1.0
    report = validate_feature_vector(fv)
    check = next(c for c in report.checks if c.name == "durations_non_negative")
    assert not check.passed


def test_detects_out_of_range_ratio(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    fv.features["free_day_ratio"] = 1.5
    report = validate_feature_vector(fv)
    check = next(c for c in report.checks if c.name == "ratios_within_expected_range")
    assert not check.passed


def test_detects_out_of_range_meq_normalized(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    fv.features["meq_normalized"] = 2.0
    report = validate_feature_vector(fv)
    check = next(c for c in report.checks if c.name == "meq_normalized_in_range")
    assert not check.passed


def test_detects_nan_value(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    fv.features["exercise_frequency_ratio"] = float("nan")
    report = validate_feature_vector(fv)
    check = next(c for c in report.checks if c.name == "no_nan_values")
    assert not check.passed


def test_detects_infinite_value(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    fv.features["caffeine_amount_mean_mg"] = float("inf")
    report = validate_feature_vector(fv)
    check = next(c for c in report.checks if c.name == "no_infinite_values")
    assert not check.passed


def test_confirms_no_sleep_onset_offset_or_midpoint_features(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    report = validate_feature_vector(fv)
    for name in (
        "no_direct_sleep_onset_feature",
        "no_direct_sleep_offset_feature",
        "no_direct_sleep_midpoint_sincos_feature",
        "no_weighted_sleep_onset_feature",
    ):
        check = next(c for c in report.checks if c.name == name)
        assert check.passed


def test_confirms_physiology_absent(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    report = validate_feature_vector(fv)
    check = next(c for c in report.checks if c.name == "physiology_absent_from_v1")
    assert check.passed


def test_raise_if_failed_raises_on_broken_vector(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    fv.features["meq_normalized"] = -5.0
    report = validate_feature_vector(fv)
    try:
        report.raise_if_failed()
        assert False, "expected AssertionError"
    except AssertionError:
        pass
