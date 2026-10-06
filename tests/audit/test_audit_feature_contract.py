"""AUDIT 5 -- Feature contract (adversarial).

Cross-checks the authoritative manifest (`app.features.feature_manifest`)
against the actual feature-vector-producing code and, critically,
*executes* the validation code (`app.features.validation.validate_feature_vector`)
against a deliberately corrupted feature vector to prove the guard
actually rejects a forbidden feature -- not just that it looks like it
would from reading the source.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import date, timedelta

import pytest

from app.features.builder import build_features
from app.features.feature_manifest import FEATURE_NAMES, MANIFEST, TOTAL_FEATURE_COUNT
from app.features.time_encoding import clock_to_sincos
from app.features.validation import validate_feature_vector
from sqlalchemy import select

from app.database.models import Participant

FIRST_TARGET_DATE = date(2026, 1, 11)


def _first_participant_id(session) -> int:
    return session.execute(select(Participant.id).order_by(Participant.id)).scalars().first()


# --- Manifest-level static checks -------------------------------------------


def test_manifest_has_exactly_68_features():
    assert TOTAL_FEATURE_COUNT == 68
    assert len(MANIFEST) == 68
    assert len(FEATURE_NAMES) == 68


def test_manifest_names_are_unique():
    assert len(FEATURE_NAMES) == len(set(FEATURE_NAMES))


def test_builder_output_names_exactly_match_manifest_names(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    assert set(fv.feature_names) == set(FEATURE_NAMES)
    assert set(fv.features.keys()) == set(FEATURE_NAMES)
    assert fv.feature_names == FEATURE_NAMES  # exact order, not just set equality


def test_no_forbidden_sleep_timing_or_physiology_feature_in_manifest():
    forbidden = ("sleep_onset", "sleep_offset", "sleep_midpoint_sin", "sleep_midpoint_cos",
                 "resting_hr", "hrv", "wrist_temp")
    for name in FEATURE_NAMES:
        for pattern in forbidden:
            assert pattern not in name, f"forbidden pattern {pattern!r} found in feature {name!r}"


def test_no_feature_encodes_the_prediction_target_directly(small_synthetic_session):
    """The prediction target is the fused DLMO hour on target_date. No
    feature name should reference dlmo/target, and no feature *value*
    should trivially equal the encoded target (would indicate a leak
    through value rather than name)."""

    pid = _first_participant_id(small_synthetic_session)
    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)

    for name in FEATURE_NAMES:
        assert "dlmo" not in name.lower(), f"feature {name!r} appears to reference the DLMO target directly"

    if fv.target_dlmo_hour is not None:
        target_sin, target_cos = clock_to_sincos(fv.target_dlmo_hour)
        for sin_name in [n for n in FEATURE_NAMES if n.endswith("_sin")]:
            cos_name = sin_name[: -len("sin")] + "cos"
            sv, cv = fv.features[sin_name], fv.features[cos_name]
            assert not (abs(sv - target_sin) < 1e-9 and abs(cv - target_cos) < 1e-9), (
                f"{sin_name}/{cos_name} exactly equals the encoded target DLMO -- target leakage"
            )


# --- Circular encoding correctness ------------------------------------------


@pytest.mark.parametrize("hour", [0.0, 6.0, 12.0, 18.0, 23.999, 3.55, 23.9999])
def test_clock_to_sincos_matches_the_documented_formula(hour):
    sin_val, cos_val = clock_to_sincos(hour)
    expected_sin = math.sin(2 * math.pi * hour / 24)
    expected_cos = math.cos(2 * math.pi * hour / 24)
    assert sin_val == pytest.approx(expected_sin, abs=1e-9)
    assert cos_val == pytest.approx(expected_cos, abs=1e-9)
    assert sin_val**2 + cos_val**2 == pytest.approx(1.0, abs=1e-9)


def test_every_circular_manifest_feature_has_a_matching_sin_cos_partner():
    circular_names = {s.name for s in MANIFEST if s.circular}
    sins = {n for n in circular_names if n.endswith("_sin") or n == "msfsc_sin"}
    for sin_name in sins:
        cos_name = sin_name[: -len("sin")] + "cos" if sin_name.endswith("sin") else None
        assert cos_name in circular_names, f"{sin_name} has no matching cos partner in the manifest"


# --- Deterministic feature ordering -----------------------------------------


def test_feature_vector_column_order_is_deterministic_across_calls(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    fv1 = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    fv2 = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    assert fv1.feature_names == fv2.feature_names == FEATURE_NAMES
    assert fv1.feature_values == fv2.feature_values


def test_feature_names_tuple_is_not_derived_from_dict_iteration_order():
    """FEATURE_NAMES must come from the manifest tuple, not from iterating
    a dict built at runtime (which, while insertion-ordered in modern
    Python, would be an implicit and fragile contract). Confirm identity
    with the manifest-derived tuple."""

    from app.features.feature_manifest import MANIFEST as manifest_now

    assert FEATURE_NAMES == tuple(spec.name for spec in manifest_now)


# --- Executable proof: the validator actually rejects a forbidden feature --


def test_validator_rejects_a_vector_with_an_injected_forbidden_sleep_onset_feature(small_synthetic_session):
    """Actively attempt to add a forbidden raw sleep-onset-hour feature
    through the real feature-vector object, then call the real validator
    and confirm it fails the check (an executable proof, not a read-through)."""

    pid = _first_participant_id(small_synthetic_session)
    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)

    corrupted_features = dict(fv.features)
    corrupted_features["sleep_onset_hour_raw"] = 23.5  # forbidden: direct sleep timing
    corrupted_names = fv.feature_names + ("sleep_onset_hour_raw",)

    corrupted_fv = replace(fv, features=corrupted_features, feature_names=corrupted_names)

    report = validate_feature_vector(corrupted_fv)
    assert not report.ok, "validator failed to reject an injected forbidden sleep_onset feature"

    failed_names = {c.name for c in report.checks if not c.passed}
    assert "no_direct_sleep_onset_feature" in failed_names
    assert "feature_count" in failed_names  # now 69 features, not 68


def test_validator_rejects_a_vector_with_an_injected_physiology_feature(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)

    corrupted_features = dict(fv.features)
    corrupted_features["resting_hr_mean"] = 60.0  # forbidden: physiology, out of scope for V1
    corrupted_names = fv.feature_names + ("resting_hr_mean",)
    corrupted_fv = replace(fv, features=corrupted_features, feature_names=corrupted_names)

    report = validate_feature_vector(corrupted_fv)
    assert not report.ok
    failed_names = {c.name for c in report.checks if not c.passed}
    assert "physiology_absent_from_v1" in failed_names


def test_validator_passes_a_genuine_unmodified_feature_vector(small_synthetic_session):
    """Negative control: the validator must not simply always fail --
    confirm a real, un-tampered vector passes every check."""

    pid = _first_participant_id(small_synthetic_session)
    fv = build_features(pid, FIRST_TARGET_DATE, small_synthetic_session)
    report = validate_feature_vector(fv)
    assert report.ok, report.summary_lines()
