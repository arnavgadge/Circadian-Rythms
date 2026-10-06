"""AUDIT 17 -- Safety pattern detection.

Covers: each of the 4 detectors in app.safety.patterns (normal vs.
pathological trajectories), the midnight-crossing false-positive check
for detect_continuous_drift, the min-observation-count boundary
(9 / 10 / 11), and flag lifecycle resolution via
app.safety.lifecycle.reconcile_flag.
"""

from __future__ import annotations

import datetime

from app.safety.config import DEFAULT_SAFETY_CONFIG
from app.safety.enums import (
    CONTINUOUS_DLMO_DRIFT,
    DETECTED,
    LOW_ALIGNMENT_DESPITE_COMPLIANCE,
    PERSISTENT_EARLY_PHASE,
    PERSISTENT_LATE_PHASE,
    PERSISTING,
    RESOLVED,
)
from app.safety.lifecycle import reconcile_flag
from app.safety.patterns import (
    DayRecord,
    PatternDetectionResult,
    detect_continuous_drift,
    detect_low_alignment_despite_compliance,
    detect_persistent_early_phase,
    detect_persistent_late_phase,
)

CFG = DEFAULT_SAFETY_CONFIG


def _dates(n, start=datetime.date(2026, 1, 1)):
    return [start + datetime.timedelta(days=i) for i in range(n)]


def _records(hours, alignment=None, compliance=None, available=True):
    dates = _dates(len(hours))
    n = len(hours)
    alignment = alignment if alignment is not None else [None] * n
    compliance = compliance if compliance is not None else [None] * n
    return [
        DayRecord(
            date=dates[i],
            prediction_available=available,
            dlmo_hour=hours[i],
            alignment_score=alignment[i],
            compliance_degree=compliance[i],
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# 1a. detect_persistent_late_phase
# ---------------------------------------------------------------------------

def test_late_phase_normal_trajectory_does_not_trigger():
    records = _records([21.0, 20.5, 21.5, 20.8, 21.2, 20.9, 21.1, 20.6, 21.3, 21.0])
    result = detect_persistent_late_phase(records, CFG)
    assert result.triggering is False


def test_late_phase_pathological_trajectory_triggers():
    # Mean DLMO well after 2:00 AM every night.
    records = _records([3.0, 3.2, 2.8, 3.5, 3.1, 2.9, 3.3, 3.0, 3.4, 3.2])
    result = detect_persistent_late_phase(records, CFG)
    assert result.triggering is True
    assert result.flag_type == PERSISTENT_LATE_PHASE


# ---------------------------------------------------------------------------
# 1b. detect_persistent_early_phase
# ---------------------------------------------------------------------------

def test_early_phase_normal_trajectory_does_not_trigger():
    records = _records([21.0, 20.5, 21.5, 20.8, 21.2, 20.9, 21.1, 20.6, 21.3, 21.0])
    result = detect_persistent_early_phase(records, CFG)
    assert result.triggering is False


def test_early_phase_pathological_trajectory_triggers():
    # Mean DLMO well before 7:30 PM every night.
    records = _records([18.0, 18.2, 17.8, 18.5, 18.1, 17.9, 18.3, 18.0, 18.4, 18.2])
    result = detect_persistent_early_phase(records, CFG)
    assert result.triggering is True
    assert result.flag_type == PERSISTENT_EARLY_PHASE


# ---------------------------------------------------------------------------
# 1c. detect_continuous_drift
# ---------------------------------------------------------------------------

def test_drift_normal_trajectory_does_not_trigger():
    records = _records([21.0, 21.1, 20.9, 21.0, 21.2, 20.8, 21.1, 21.0, 20.9, 21.0])
    result = detect_continuous_drift(records, CFG)
    assert result.triggering is False


def test_drift_pathological_trajectory_triggers():
    # +30 min/day, well above the 20 min/day threshold.
    hours = [20.0 + 0.5 * i for i in range(10)]
    records = _records(hours)
    result = detect_continuous_drift(records, CFG)
    assert result.triggering is True
    assert result.triggering_statistics["trend_minutes_per_day"] > CFG.drift_threshold_minutes_per_day


def test_drift_midnight_crossing_does_not_false_trigger():
    """Critical adversarial case: dlmo_hour legitimately oscillates
    across the midnight boundary (23:50 <-> 00:10) night to night with
    no real underlying drift. A naive raw-hour trend fit would see huge
    swings (~23.6h) and false-trigger; the circular unwrap must prevent
    that."""

    hours = [23.833, 0.1667] * 6  # 12 nights, alternating 23:50 / 00:10
    records = _records(hours[:12])
    result = detect_continuous_drift(records, CFG)
    trend = result.triggering_statistics["trend_minutes_per_day"]
    assert result.triggering is False
    assert trend is not None
    assert abs(trend) < 5.0


# ---------------------------------------------------------------------------
# 1d. detect_low_alignment_despite_compliance
# ---------------------------------------------------------------------------

def test_low_alignment_normal_trajectory_does_not_trigger():
    # High alignment despite high compliance -- not a concerning pattern.
    records = _records(
        [21.0] * 10,
        alignment=[80.0] * 10,
        compliance=[0.85] * 10,
    )
    result = detect_low_alignment_despite_compliance(records, CFG)
    assert result.triggering is False


def test_low_alignment_pathological_trajectory_triggers():
    # Low alignment despite high compliance -- the concerning pattern.
    records = _records(
        [21.0] * 10,
        alignment=[30.0] * 10,
        compliance=[0.85] * 10,
    )
    result = detect_low_alignment_despite_compliance(records, CFG)
    assert result.triggering is True
    assert result.flag_type == LOW_ALIGNMENT_DESPITE_COMPLIANCE


# ---------------------------------------------------------------------------
# 2. Minimum-observation-count boundary: 9 / 10 / 11.
# ---------------------------------------------------------------------------

def test_insufficient_observations_below_minimum():
    hours = [3.0 + 0.1 * i for i in range(CFG.min_observations_for_flag - 1)]  # 9 obs, late-phase-shaped
    records = _records(hours)
    result = detect_persistent_late_phase(records, CFG)
    assert result.n_observations == 9
    assert result.triggering is False
    assert result.triggering_statistics.get("reason") == "insufficient_observations"


def test_triggers_at_exactly_minimum_observations():
    hours = [3.0 + 0.1 * i for i in range(CFG.min_observations_for_flag)]  # 10 obs
    records = _records(hours)
    result = detect_persistent_late_phase(records, CFG)
    assert result.n_observations == 10
    assert result.triggering is True


def test_triggers_above_minimum_observations():
    hours = [3.0 + 0.1 * i for i in range(CFG.min_observations_for_flag + 1)]  # 11 obs
    records = _records(hours)
    result = detect_persistent_late_phase(records, CFG)
    assert result.n_observations == 11
    assert result.triggering is True


# ---------------------------------------------------------------------------
# 3. Flag lifecycle resolution.
# ---------------------------------------------------------------------------

def test_reconcile_flag_detected_when_no_existing_flag():
    detection = PatternDetectionResult(PERSISTENT_LATE_PHASE, True, 10, {})
    decision = reconcile_flag(detection, has_existing_open_flag=False, resolution_check=None, config=CFG)
    assert decision.lifecycle_state == DETECTED


def test_reconcile_flag_persisting_while_still_triggering():
    detection = PatternDetectionResult(PERSISTENT_LATE_PHASE, True, 10, {})
    decision = reconcile_flag(detection, has_existing_open_flag=True, resolution_check=None, config=CFG)
    assert decision.lifecycle_state == PERSISTING


def test_reconcile_flag_resolved_after_sustained_return_to_normal():
    detection = PatternDetectionResult(PERSISTENT_LATE_PHASE, False, 14, {})
    # 7 clean (non-triggering) trailing observations -- resolution confirmed.
    resolution_check = PatternDetectionResult(PERSISTENT_LATE_PHASE, False, 7, {})
    decision = reconcile_flag(detection, has_existing_open_flag=True, resolution_check=resolution_check, config=CFG)
    assert decision.lifecycle_state == RESOLVED


def test_reconcile_flag_not_resolved_with_partial_return_to_normal():
    # Full window no longer triggers, but the trailing resolution window
    # still does -- must stay PERSISTING, not resolve on a partial recovery.
    detection = PatternDetectionResult(PERSISTENT_LATE_PHASE, False, 14, {})
    resolution_check = PatternDetectionResult(PERSISTENT_LATE_PHASE, True, 7, {})
    decision = reconcile_flag(detection, has_existing_open_flag=True, resolution_check=resolution_check, config=CFG)
    assert decision.lifecycle_state == PERSISTING


def test_reconcile_flag_none_when_nothing_to_report():
    detection = PatternDetectionResult(PERSISTENT_LATE_PHASE, False, 14, {})
    decision = reconcile_flag(detection, has_existing_open_flag=False, resolution_check=None, config=CFG)
    assert decision is None


def test_reconcile_flag_severity_assignment():
    # continuous_dlmo_drift is the one locked HIGH-severity flag type.
    drift_detection = PatternDetectionResult(CONTINUOUS_DLMO_DRIFT, True, 10, {})
    decision = reconcile_flag(drift_detection, has_existing_open_flag=False, resolution_check=None, config=CFG)
    assert decision.severity == "HIGH"

    late_detection = PatternDetectionResult(PERSISTENT_LATE_PHASE, True, 10, {})
    decision = reconcile_flag(late_detection, has_existing_open_flag=False, resolution_check=None, config=CFG)
    assert decision.severity == "MODERATE"
