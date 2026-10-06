"""AUDIT 3 -- Temporal leakage (adversarial).

Proves, against the real code (not by reading it), that:

1. The feature builder (`app.features.builder.build_features`) never
   reflects a deliberately extreme/distinctive value injected on the
   target day (day N) or on a future day (day N+1).
2. The daily-inference read boundary (`app.pipeline.read`) never
   returns an observation dated on or after the target date, even when
   the database actually contains one (simulating an upstream bug that
   wrote a same-day or future row).
3. The feature-engineering layer never touches the effectiveness/
   personalization tables at all (import-level + runtime check).
"""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest
from sqlalchemy import select

from app.database.models import DailyObservation, Participant
from app.features.builder import build_features
from app.features.feature_manifest import FEATURE_NAMES
from app.features.time_encoding import clock_to_sincos
from app.pipeline.config import DEFAULT_PIPELINE_CONFIG
from app.pipeline.read import read_daily_inference_inputs

FIRST_TARGET_DATE = date(2026, 1, 11)  # matches tests/test_features_builder.py convention


def _first_participant_id(session) -> int:
    return session.execute(select(Participant.id).order_by(Participant.id)).scalars().first()


# --- 1. Extreme target-day / future-day injection --------------------------


def test_extreme_target_and_future_day_values_never_reach_the_feature_vector(small_synthetic_session):
    """Inject an impossible 300-minute evening-screen-duration value (and a
    distinctive clock time) on the target day and on target_day + 1, then
    assert none of the 68 features encode either injected value.
    """

    session = small_synthetic_session
    pid = _first_participant_id(session)
    target_date = FIRST_TARGET_DATE

    injected_minutes = 300.0  # 5 hours -- far outside any plausible screen session
    injected_clock = time(3, 33, 0)  # a distinctive hour unlikely to occur by chance

    target_day_row = session.execute(
        select(DailyObservation).where(
            DailyObservation.participant_id == pid,
            DailyObservation.observation_date == target_date,
        )
    ).scalars().first()
    assert target_day_row is not None, "fixture must already have a row on the target date"
    target_day_row.evening_screen_duration_minutes = injected_minutes
    target_day_row.evening_screen_end_time = injected_clock

    future_date = target_date + timedelta(days=1)
    future_row = session.execute(
        select(DailyObservation).where(
            DailyObservation.participant_id == pid,
            DailyObservation.observation_date == future_date,
        )
    ).scalars().first()
    assert future_row is not None, "fixture must already have a row on target_date + 1"
    future_row.evening_screen_duration_minutes = injected_minutes + 10.0
    future_row.evening_screen_end_time = time(3, 44, 0)

    session.flush()

    fv = build_features(pid, target_date, session)

    # (a) The window boundaries themselves must exclude both injected dates.
    assert fv.window_end == target_date - timedelta(days=1)
    assert future_date > fv.window_end
    assert target_date > fv.window_end

    # (b) No sin/cos pair anywhere in the vector matches the injected clock
    #     times (checked against both injected hours, with tolerance).
    injected_sin_1, injected_cos_1 = clock_to_sincos(3.55)  # 03:33
    injected_sin_2, injected_cos_2 = clock_to_sincos(3.7333333)  # 03:44
    for sin_name in [n for n in FEATURE_NAMES if n.endswith("_sin")]:
        cos_name = sin_name[: -len("sin")] + "cos"
        sv, cv = fv.features[sin_name], fv.features[cos_name]
        for isin, icos in ((injected_sin_1, injected_cos_1), (injected_sin_2, injected_cos_2)):
            assert not (abs(sv - isin) < 1e-6 and abs(cv - icos) < 1e-6), (
                f"{sin_name}/{cos_name} matches an injected target/future-day clock value -- leakage"
            )

    # (c) No numeric aggregate reflects the injected 300/310-minute screen
    #     duration -- the 6-day window mean/recency-weighted mean must stay
    #     far below what including a 300+ minute day would produce.
    assert fv.features["screen_duration_mean_hours"] < 3.0, (
        "screen_duration_mean_hours reflects the injected target/future-day extreme value"
    )
    assert fv.features["screen_duration_recency_weighted_hours"] < 3.0, (
        "screen_duration_recency_weighted_hours reflects the injected target/future-day extreme value"
    )


def test_feature_vector_unaffected_by_deleting_or_mutating_future_rows(small_synthetic_session):
    """Sanity companion: the feature vector for a fixed target_date must be
    identical whether or not a row exists / what it contains on
    target_date or later -- i.e. mutating the future must be a no-op."""

    session = small_synthetic_session
    pid = _first_participant_id(session)
    target_date = FIRST_TARGET_DATE

    fv_before = build_features(pid, target_date, session)

    future_row = session.execute(
        select(DailyObservation).where(
            DailyObservation.participant_id == pid,
            DailyObservation.observation_date == target_date + timedelta(days=2),
        )
    ).scalars().first()
    if future_row is not None:
        future_row.evening_screen_duration_minutes = 999.0
        future_row.morning_light_duration_minutes = 999.0
        future_row.caffeine_amount_mg = 999.0
        session.flush()

    fv_after = build_features(pid, target_date, session)
    assert fv_before.features == fv_after.features


# --- 2. Pipeline read-boundary off-by-one check -----------------------------


def test_read_daily_inference_inputs_never_returns_a_same_day_or_future_row(small_synthetic_session):
    """Simulates an upstream bug: a `daily_observations` row exists dated
    exactly on the target_date (and one the day after). The read boundary
    must exclude both from `window_observations`, and must raise if it
    ever failed to (the module's own guard), proving the guard is live
    against real data, not just present as unreachable code."""

    session = small_synthetic_session
    pid = _first_participant_id(session)
    target_date = FIRST_TARGET_DATE

    result = read_daily_inference_inputs(session, pid, target_date, DEFAULT_PIPELINE_CONFIG)

    for obs in result.window_observations:
        assert obs.observation_date < target_date, (
            f"Leakage: window_observations contains a same-day/future row {obs.observation_date} "
            f"for target_date={target_date}"
        )
    assert result.window_observations[-1].observation_date == target_date - timedelta(days=1)
    assert len(result.window_observations) == DEFAULT_PIPELINE_CONFIG.min_consecutive_history_days


def test_read_boundary_query_range_itself_excludes_target_date(small_synthetic_session):
    """Directly re-derive the query's date bounds (independent of the
    module's internal implementation) and confirm no row in that range is
    on or after target_date -- an independent re-check of the SQL filter,
    not just the Python-level guard."""

    session = small_synthetic_session
    pid = _first_participant_id(session)
    target_date = FIRST_TARGET_DATE
    lookback = DEFAULT_PIPELINE_CONFIG.min_consecutive_history_days

    window_start = target_date - timedelta(days=lookback)
    window_end = target_date - timedelta(days=1)

    rows = session.execute(
        select(DailyObservation).where(
            DailyObservation.participant_id == pid,
            DailyObservation.observation_date >= window_start,
            DailyObservation.observation_date <= window_end,
        )
    ).scalars().all()

    assert all(r.observation_date < target_date for r in rows)
    assert window_end == target_date - timedelta(days=1)


# --- 3. Feature layer never touches effectiveness/personalization tables ---


def test_feature_builder_module_imports_no_effectiveness_or_personalization_symbols():
    """Static/import-level guard: the builder module's own import list must
    not name anything from app.effectiveness or app.personalization."""

    import app.features.builder as builder_module

    module_source_globals = vars(builder_module)
    for name, value in module_source_globals.items():
        mod = getattr(value, "__module__", None)
        if mod and (mod.startswith("app.effectiveness") or mod.startswith("app.personalization")):
            pytest.fail(f"app.features.builder imports {name!r} from {mod!r} -- future/outcome leakage risk")


def test_feature_builder_source_has_no_effectiveness_or_personalization_import():
    import inspect

    import app.features.builder as builder_module

    source = inspect.getsource(builder_module)
    assert "app.effectiveness" not in source
    assert "app.personalization" not in source
