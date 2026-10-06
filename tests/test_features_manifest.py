"""Tests for the authoritative feature manifest."""

from __future__ import annotations

from app.features.feature_manifest import (
    FEATURE_NAMES,
    MANIFEST,
    RAW_DAILY_SIGNALS,
    TOTAL_FEATURE_COUNT,
    feature_spec,
    features_by_tier,
)


def test_manifest_has_exactly_68_features():
    assert len(MANIFEST) == 68
    assert TOTAL_FEATURE_COUNT == 68


def test_feature_names_are_unique():
    assert len(FEATURE_NAMES) == len(set(FEATURE_NAMES))


def test_raw_daily_signals_contribute_exactly_48_features():
    raw_count = sum(1 for spec in MANIFEST if spec.aggregation == "raw")
    assert raw_count == 4 * 6 * 2  # 4 signals x 6 days x (sin, cos)
    assert len(RAW_DAILY_SIGNALS) == 4


def test_no_forbidden_sleep_or_physiology_features():
    forbidden_patterns = ("sleep_onset", "sleep_offset", "sleep_midpoint_sin", "sleep_midpoint_cos", "resting_hr", "hrv", "wrist_temp")
    for name in FEATURE_NAMES:
        for pattern in forbidden_patterns:
            assert pattern not in name, f"{name} matches forbidden pattern {pattern}"


def test_sleep_onset_is_not_used_as_the_fourth_raw_signal():
    signal_keys = [key for key, *_ in RAW_DAILY_SIGNALS]
    assert "sleep_onset" not in signal_keys
    assert "exercise_time" in signal_keys  # the chosen fourth signal


def test_every_feature_has_a_tier():
    for spec in MANIFEST:
        assert spec.tier in ("tier_1", "tier_2", "tier_3", "n/a")


def test_tier_lookup_helper():
    tier1 = features_by_tier("tier_1")
    assert len(tier1) > 0
    assert all(spec.tier == "tier_1" for spec in tier1)


def test_feature_spec_lookup():
    spec = feature_spec("meq_normalized")
    assert spec.name == "meq_normalized"
    assert spec.circular is False


def test_circular_features_have_no_non_circular_reason_required():
    for spec in MANIFEST:
        if not spec.circular:
            assert spec.non_circular_reason, f"{spec.name} is non-circular but has no reason documented"


def test_msfsc_and_meq_features_present():
    assert "msfsc_sin" in FEATURE_NAMES
    assert "msfsc_cos" in FEATURE_NAMES
    assert "meq_normalized" in FEATURE_NAMES
    assert "meq_msfsc_divergence" in FEATURE_NAMES


def test_recency_weighted_features_count_is_six():
    recency = [s for s in MANIFEST if s.aggregation == "recency_weighted_mean"]
    assert len(recency) == 6
