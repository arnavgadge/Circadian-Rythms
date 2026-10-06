"""Tests for Layer 3: the biological continuity constraint."""

from __future__ import annotations

import pytest

from app.fusion.continuity import apply_continuity_cap


def _hm(hour: int, minute: int) -> float:
    return hour + minute / 60.0


# --- 14. Continuity cap ---

def test_small_move_within_cap_is_unchanged():
    result = apply_continuity_cap(proposed_hour=10.2, previous_hour=10.0, cap_minutes=60.0)
    assert result.applied is False
    assert result.final_hour == pytest.approx(10.2)


def test_move_beyond_cap_is_limited():
    result = apply_continuity_cap(proposed_hour=12.0, previous_hour=10.0, cap_minutes=60.0)
    assert result.applied is True
    assert result.final_hour == pytest.approx(11.0, abs=1e-6)


def test_exact_cap_boundary_is_accepted_unchanged():
    # previous=23:50, proposed=00:50 -> exactly +60 minutes -> accepted.
    result = apply_continuity_cap(_hm(0, 50), _hm(23, 50), cap_minutes=60.0)
    assert result.applied is False
    assert result.final_hour == pytest.approx(_hm(0, 50), abs=1e-6)


# --- 15. Midnight continuity cap ---

def test_midnight_crossing_continuity_cap_worked_example():
    """previous=23:50, proposed=02:00 (~+130 min), cap=60 -> final ~= 00:50."""

    result = apply_continuity_cap(proposed_hour=2.0, previous_hour=_hm(23, 50), cap_minutes=60.0)
    assert result.applied is True
    assert result.final_hour == pytest.approx(_hm(0, 50), abs=1e-6)


def test_continuity_cap_handles_negative_direction_across_midnight():
    # previous=00:10, proposed=22:00 (i.e. -130 min backward) with a 60 min cap
    # should limit to previous - 60min = 23:10.
    result = apply_continuity_cap(proposed_hour=22.0, previous_hour=_hm(0, 10), cap_minutes=60.0)
    assert result.applied is True
    assert result.final_hour == pytest.approx(_hm(23, 10), abs=1e-6)


# --- 16. Disagreement-specific continuity caps ---

@pytest.mark.parametrize("cap_minutes", [60.0, 45.0, 30.0, 20.0])
def test_continuity_cap_respects_configured_value(cap_minutes):
    # A large proposed jump (3 hours) should always be limited to exactly
    # the configured cap, regardless of which regime's cap is passed in.
    result = apply_continuity_cap(proposed_hour=13.0, previous_hour=10.0, cap_minutes=cap_minutes)
    assert result.applied is True
    expected_hour = 10.0 + cap_minutes / 60.0
    assert result.final_hour == pytest.approx(expected_hour, abs=1e-6)


def test_continuity_never_uses_naive_numeric_comparison():
    # A naive |proposed - previous| using raw hour floats would see
    # 23:50 -> 00:05 as a huge negative jump (-23.75h); the real circular
    # distance is only +15 minutes, well within a 60 min cap.
    result = apply_continuity_cap(proposed_hour=_hm(0, 5), previous_hour=_hm(23, 50), cap_minutes=60.0)
    assert result.applied is False
