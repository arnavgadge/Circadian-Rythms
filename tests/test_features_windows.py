"""Tests for six-day window identification."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.features.windows import Window, compute_valid_windows


def test_window_validates_consecutive_days():
    dates = tuple(date(2026, 1, 1) + timedelta(days=i) for i in range(6))
    w = Window(
        participant_id=1,
        window_start=dates[0],
        window_end=dates[-1],
        target_date=dates[-1] + timedelta(days=1),
        day_dates=dates,
    )
    assert w.day_dates[0] == date(2026, 1, 1)
    assert w.day_dates[-1] == date(2026, 1, 6)
    assert w.target_date == date(2026, 1, 7)


def test_window_rejects_non_consecutive_days():
    dates = (date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 4), date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7))
    with pytest.raises(ValueError):
        Window(participant_id=1, window_start=dates[0], window_end=dates[-1], target_date=date(2026, 1, 8), day_dates=dates)


def test_window_rejects_wrong_day_count():
    dates = tuple(date(2026, 1, 1) + timedelta(days=i) for i in range(5))
    with pytest.raises(ValueError):
        Window(participant_id=1, window_start=dates[0], window_end=dates[-1], target_date=date(2026, 1, 6), day_dates=dates)


def test_window_rejects_target_date_not_immediately_after_window_end():
    dates = tuple(date(2026, 1, 1) + timedelta(days=i) for i in range(6))
    with pytest.raises(ValueError):
        Window(participant_id=1, window_start=dates[0], window_end=dates[-1], target_date=date(2026, 1, 10), day_dates=dates)


def test_compute_valid_windows_produces_24_windows_for_30_consecutive_days():
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(30)]
    windows = compute_valid_windows(participant_id=1, available_dates=dates, window_size_days=6)
    assert len(windows) == 24


def test_compute_valid_windows_first_and_last_window_targets():
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(30)]
    windows = compute_valid_windows(participant_id=1, available_dates=dates, window_size_days=6)

    first = windows[0]
    assert first.window_start == date(2026, 1, 1)
    assert first.window_end == date(2026, 1, 6)
    assert first.target_date == date(2026, 1, 7)

    last = windows[-1]
    assert last.window_start == date(2026, 1, 24)
    assert last.window_end == date(2026, 1, 29)
    assert last.target_date == date(2026, 1, 30)


def test_compute_valid_windows_preserves_oldest_to_newest_ordering():
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(10)]
    windows = compute_valid_windows(participant_id=1, available_dates=dates, window_size_days=6)
    for w in windows:
        assert list(w.day_dates) == sorted(w.day_dates)
        assert w.day_dates[0] < w.day_dates[-1]


def test_compute_valid_windows_skips_across_a_gap():
    # A 3-day gap between day 10 and day 14 should prevent any window
    # from spanning across it.
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(10)]
    dates += [date(2026, 1, 14) + timedelta(days=i) for i in range(10)]
    windows = compute_valid_windows(participant_id=1, available_dates=dates, window_size_days=6)
    for w in windows:
        for d in w.day_dates + (w.target_date,):
            assert d not in (date(2026, 1, 11), date(2026, 1, 12), date(2026, 1, 13))


def test_compute_valid_windows_handles_unsorted_duplicate_input():
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(7)]
    shuffled = dates[::-1] + [dates[0]]  # reversed, plus a duplicate
    windows = compute_valid_windows(participant_id=1, available_dates=shuffled, window_size_days=6)
    assert len(windows) == 1
    assert windows[0].target_date == date(2026, 1, 7)
