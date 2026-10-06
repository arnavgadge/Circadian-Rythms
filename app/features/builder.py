"""The Version-1 feature builder.

Turns exactly six previous complete days of a participant's raw
behavioral history into the 68-feature vector defined by
``app.features.feature_manifest.MANIFEST``. Reads directly from the
Phase 2 database (``daily_observations`` + ``participant_profiles`` +
``circadian_labels``); never touches ``physiology_logs`` anywhere in
this module -- that is how Version 1's physiology exclusion is
enforced structurally, not just by convention.

No randomness, and no global fitting: every value is computed from
that participant's own window (plus, only when needed, that
participant's own history strictly before the window -- see
``app.features.imputation``). Given the same database contents, the
same call always returns the same vector.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import CircadianLabel, DailyObservation, ParticipantProfile
from app.features.aggregation import flat_mean, flat_std, ratio, recency_weighted_mean
from app.features.config import DEFAULT_FEATURE_CONFIG, FeatureConfig
from app.features.feature_manifest import FEATURE_NAMES, RAW_DAILY_SIGNALS, TOTAL_FEATURE_COUNT
from app.features.imputation import ImputationRecord, resolve_circular, resolve_numeric
from app.features.time_encoding import clock_to_sincos
from app.features.windows import Window
from app.synthetic.time_utils import circular_diff_hours, circular_mean_hours, clock_time_to_hour


@dataclass
class FeatureVector:
    """One feature-engineered row: a participant/target-date pair's 68 features."""

    participant_id: int
    target_date: date
    window_start: date
    window_end: date

    feature_names: tuple
    features: dict  # name -> float, always fully populated (no NaN)

    missing_features: list
    imputed_features: list
    imputation_methods: dict
    tier_missing_counts: dict
    completeness: float

    target_dlmo_hour: Optional[float] = None

    @property
    def feature_values(self) -> tuple:
        """Feature values in ``feature_names`` (manifest) order -- the X row."""

        return tuple(self.features[name] for name in self.feature_names)


def _day_rows(session: Session, participant_id: int, day_dates: tuple) -> dict:
    rows = session.execute(
        select(DailyObservation).where(
            DailyObservation.participant_id == participant_id,
            DailyObservation.observation_date.in_(day_dates),
        )
    ).scalars().all()
    return {row.observation_date: row for row in rows}


def _personal_history_last_clock_time_hour(
    session: Session, participant_id: int, window_start: date, column
) -> Optional[float]:
    row = session.execute(
        select(column)
        .where(
            DailyObservation.participant_id == participant_id,
            DailyObservation.observation_date < window_start,
            column.isnot(None),
        )
        .order_by(DailyObservation.observation_date.desc())
        .limit(1)
    ).first()
    if row is None or row[0] is None:
        return None
    return clock_time_to_hour(row[0])


def _personal_history_numeric_mean(
    session: Session, participant_id: int, window_start: date, column
) -> Optional[float]:
    values = session.execute(
        select(column).where(
            DailyObservation.participant_id == participant_id,
            DailyObservation.observation_date < window_start,
            column.isnot(None),
        )
    ).scalars().all()
    return flat_mean(list(values)) if values else None


def _personal_history_msfsc_hour(session: Session, participant_id: int, window_start: date) -> Optional[float]:
    values = session.execute(
        select(DailyObservation.free_day_sleep_midpoint_time).where(
            DailyObservation.participant_id == participant_id,
            DailyObservation.observation_date < window_start,
            DailyObservation.is_free_day.is_(True),
            DailyObservation.free_day_sleep_midpoint_time.isnot(None),
        )
    ).scalars().all()
    if not values:
        return None
    return circular_mean_hours([clock_time_to_hour(v) for v in values])


def _personal_history_free_day_ratio(session: Session, participant_id: int, window_start: date) -> Optional[float]:
    values = session.execute(
        select(DailyObservation.is_free_day).where(
            DailyObservation.participant_id == participant_id,
            DailyObservation.observation_date < window_start,
            DailyObservation.is_free_day.isnot(None),
        )
    ).scalars().all()
    if not values:
        return None
    return sum(1 for v in values if v) / len(values)


def _personal_history_exercise_frequency(session: Session, participant_id: int, window_start: date) -> Optional[float]:
    values = session.execute(
        select(DailyObservation.exercise_duration_minutes).where(
            DailyObservation.participant_id == participant_id,
            DailyObservation.observation_date < window_start,
            DailyObservation.exercise_duration_minutes.isnot(None),
        )
    ).scalars().all()
    if not values:
        return None
    return sum(1 for v in values if v > 0) / len(values)


_RAW_SIGNAL_COLUMN = {
    "evening_screen_end_time": DailyObservation.evening_screen_end_time,
    "last_meal_time": DailyObservation.last_meal_time,
    "morning_light_start_time": DailyObservation.morning_light_start_time,
    "exercise_time": DailyObservation.exercise_time,
}


def build_features(
    participant_id: int,
    target_date: date,
    session: Session,
    config: FeatureConfig = DEFAULT_FEATURE_CONFIG,
) -> FeatureVector:
    """Build the 68-feature vector for ``participant_id`` predicting ``target_date``.

    Uses exactly the six days ``target_date - 6`` .. ``target_date - 1``
    (oldest to newest) -- never ``target_date`` itself.
    """

    window_end = target_date - timedelta(days=1)
    window_start = target_date - timedelta(days=config.window_size_days)
    day_dates = tuple(window_start + timedelta(days=i) for i in range(config.window_size_days))

    window = Window(
        participant_id=participant_id,
        window_start=window_start,
        window_end=window_end,
        target_date=target_date,
        day_dates=day_dates,
    )

    # Explicit leakage guard, matching the brief's example assertion.
    assert max(window.day_dates) == target_date - timedelta(days=1), (
        "Leakage guard failed: feature window must end exactly one day before target_date."
    )
    assert min(window.day_dates) == target_date - timedelta(days=config.window_size_days)

    rows_by_date = _day_rows(session, participant_id, day_dates)
    record = ImputationRecord()
    features: dict = {}

    # --- Group 1: raw daily circular signals (48) ---
    for signal_key, source_signal, tier, _purpose in RAW_DAILY_SIGNALS:
        column = _RAW_SIGNAL_COLUMN[source_signal]
        for day_index, day_date in enumerate(day_dates, start=1):
            sin_name = f"{signal_key}_day_{day_index}_sin"
            cos_name = f"{signal_key}_day_{day_index}_cos"

            row = rows_by_date.get(day_date)
            raw_value = getattr(row, column.key) if row is not None else None
            window_hour = clock_time_to_hour(raw_value) if raw_value is not None else None

            if window_hour is None:
                history_hour = _personal_history_last_clock_time_hour(
                    session, participant_id, window_start, column
                )
            else:
                history_hour = None

            default_hour = getattr(config, f"default_{signal_key}_hour")

            resolved_hour = resolve_circular(
                window_hour, history_hour, default_hour, sin_name, cos_name, tier, record
            )
            sin_val, cos_val = clock_to_sincos(resolved_hour)
            features[sin_name] = sin_val
            features[cos_name] = cos_val

    # --- Group 2: MSFsc (2) ---
    window_free_midpoints = [
        clock_time_to_hour(row.free_day_sleep_midpoint_time)
        for day_date, row in rows_by_date.items()
        if row is not None and row.is_free_day and row.free_day_sleep_midpoint_time is not None
    ]
    window_msfsc_hour = circular_mean_hours(window_free_midpoints) if window_free_midpoints else None
    if window_msfsc_hour is None:
        history_msfsc_hour = _personal_history_msfsc_hour(session, participant_id, window_start)
    else:
        history_msfsc_hour = None
    resolved_msfsc_hour = resolve_circular(
        window_msfsc_hour, history_msfsc_hour, config.default_msfsc_hour, "msfsc_sin", "msfsc_cos", "tier_1", record
    )
    msfsc_sin, msfsc_cos = clock_to_sincos(resolved_msfsc_hour)
    features["msfsc_sin"] = msfsc_sin
    features["msfsc_cos"] = msfsc_cos

    # --- Group 3: MEQ-derived (2) ---
    profile = session.get(ParticipantProfile, participant_id)
    meq_raw = profile.meq_score if profile is not None else None
    resolved_meq = resolve_numeric(
        meq_raw, None, config.default_meq_score, "meq_normalized", "tier_2", record
    )
    meq_normalized = (resolved_meq - config.meq_min) / (config.meq_max - config.meq_min)
    features["meq_normalized"] = meq_normalized

    expected_msfsc_from_meq = config.meq_evening_type_msfsc_hour + (
        (resolved_meq - config.meq_min)
        / (config.meq_max - config.meq_min)
        * (config.meq_morning_type_msfsc_hour - config.meq_evening_type_msfsc_hour)
    )
    features["meq_msfsc_divergence"] = circular_diff_hours(resolved_msfsc_hour, expected_msfsc_from_meq)

    # --- Groups 4 & 5: flat + recency-weighted window aggregates ---
    _build_window_aggregates(features, record, rows_by_date, day_dates, session, participant_id, window_start, config)

    missing_features = list(dict.fromkeys(record.missing_features))  # de-dup, preserve order
    imputed_features = list(dict.fromkeys(record.imputed_features))
    completeness = 1.0 - (len(missing_features) / TOTAL_FEATURE_COUNT)

    target_label = session.execute(
        select(CircadianLabel).where(
            CircadianLabel.participant_id == participant_id,
            CircadianLabel.target_date == target_date,
            CircadianLabel.is_latest.is_(True),
        )
    ).scalars().first()
    target_dlmo_hour = (
        clock_time_to_hour(target_label.fused_dlmo_time)
        if target_label is not None and target_label.fused_dlmo_time is not None
        else None
    )

    ordered_features = {name: features[name] for name in FEATURE_NAMES}

    return FeatureVector(
        participant_id=participant_id,
        target_date=target_date,
        window_start=window_start,
        window_end=window_end,
        feature_names=FEATURE_NAMES,
        features=ordered_features,
        missing_features=missing_features,
        imputed_features=imputed_features,
        imputation_methods=dict(record.imputation_methods),
        tier_missing_counts=dict(record.tier_missing_counts),
        completeness=completeness,
        target_dlmo_hour=target_dlmo_hour,
    )


def _build_window_aggregates(
    features: dict,
    record: ImputationRecord,
    rows_by_date: dict,
    day_dates: tuple,
    session: Session,
    participant_id: int,
    window_start: date,
    config: FeatureConfig,
) -> None:
    def day_values(attr: str) -> list:
        return [
            getattr(rows_by_date[d], attr) if rows_by_date.get(d) is not None else None for d in day_dates
        ]

    def resolve_flat(values, agg_fn, feature_name, tier, history_fn, default):
        computed = agg_fn(values)
        if computed is None:
            history_value = history_fn()
        else:
            history_value = None
        return resolve_numeric(computed, history_value, default, feature_name, tier, record)

    sleep_duration_minutes = day_values("sleep_duration_minutes")
    sleep_duration_hours = [v / 60.0 if v is not None else None for v in sleep_duration_minutes]
    features["sleep_duration_mean_hours"] = resolve_flat(
        sleep_duration_hours, flat_mean, "sleep_duration_mean_hours", "tier_3",
        lambda: _hours(_personal_history_numeric_mean(session, participant_id, window_start, DailyObservation.sleep_duration_minutes)),
        config.default_sleep_duration_hours,
    )
    features["sleep_duration_std_hours"] = resolve_flat(
        sleep_duration_hours, flat_std, "sleep_duration_std_hours", "tier_3",
        lambda: None,  # variance-of-history is not implemented; falls through to population default
        0.0,
    )
    features["sleep_duration_recency_weighted_hours"] = resolve_flat(
        sleep_duration_hours, recency_weighted_mean, "sleep_duration_recency_weighted_hours", "tier_3",
        lambda: features["sleep_duration_mean_hours"],
        config.default_sleep_duration_hours,
    )

    variability = day_values("sleep_midpoint_variability_minutes")
    features["sleep_midpoint_variability_mean_minutes"] = resolve_flat(
        variability, flat_mean, "sleep_midpoint_variability_mean_minutes", "tier_3",
        lambda: _personal_history_numeric_mean(session, participant_id, window_start, DailyObservation.sleep_midpoint_variability_minutes),
        config.default_sleep_midpoint_variability_minutes,
    )
    features["sleep_midpoint_variability_recency_weighted_minutes"] = resolve_flat(
        variability, recency_weighted_mean, "sleep_midpoint_variability_recency_weighted_minutes", "tier_3",
        lambda: features["sleep_midpoint_variability_mean_minutes"],
        config.default_sleep_midpoint_variability_minutes,
    )

    screen_minutes = day_values("evening_screen_duration_minutes")
    screen_hours = [v / 60.0 if v is not None else None for v in screen_minutes]
    features["screen_duration_mean_hours"] = resolve_flat(
        screen_hours, flat_mean, "screen_duration_mean_hours", "tier_1",
        lambda: _hours(_personal_history_numeric_mean(session, participant_id, window_start, DailyObservation.evening_screen_duration_minutes)),
        config.default_screen_duration_hours,
    )
    features["screen_duration_recency_weighted_hours"] = resolve_flat(
        screen_hours, recency_weighted_mean, "screen_duration_recency_weighted_hours", "tier_1",
        lambda: features["screen_duration_mean_hours"],
        config.default_screen_duration_hours,
    )

    light_minutes = day_values("morning_light_duration_minutes")
    features["morning_light_duration_mean_minutes"] = resolve_flat(
        light_minutes, flat_mean, "morning_light_duration_mean_minutes", "tier_1",
        lambda: _personal_history_numeric_mean(session, participant_id, window_start, DailyObservation.morning_light_duration_minutes),
        config.default_morning_light_duration_minutes,
    )
    features["morning_light_duration_recency_weighted_minutes"] = resolve_flat(
        light_minutes, recency_weighted_mean, "morning_light_duration_recency_weighted_minutes", "tier_1",
        lambda: features["morning_light_duration_mean_minutes"],
        config.default_morning_light_duration_minutes,
    )

    exercise_minutes = day_values("exercise_duration_minutes")
    exercising_days = [v for v in exercise_minutes if v is not None and v > 0]
    features["exercise_duration_mean_minutes"] = resolve_flat(
        exercising_days if exercising_days else [None] * len(exercise_minutes),
        flat_mean, "exercise_duration_mean_minutes", "tier_3",
        lambda: _personal_history_numeric_mean(session, participant_id, window_start, DailyObservation.exercise_duration_minutes),
        config.default_exercise_duration_minutes,
    )
    known_exercise_days = [v for v in exercise_minutes if v is not None]
    freq = ratio(sum(1 for v in known_exercise_days if v > 0), len(known_exercise_days))
    features["exercise_frequency_ratio"] = resolve_flat(
        [freq], lambda vs: vs[0], "exercise_frequency_ratio", "tier_3",
        lambda: _personal_history_exercise_frequency(session, participant_id, window_start),
        config.default_exercise_frequency_ratio,
    )

    caffeine_mg = day_values("caffeine_amount_mg")
    features["caffeine_amount_mean_mg"] = resolve_flat(
        caffeine_mg, flat_mean, "caffeine_amount_mean_mg", "tier_3",
        lambda: _personal_history_numeric_mean(session, participant_id, window_start, DailyObservation.caffeine_amount_mg),
        config.default_caffeine_amount_mg,
    )
    features["caffeine_amount_recency_weighted_mg"] = resolve_flat(
        caffeine_mg, recency_weighted_mean, "caffeine_amount_recency_weighted_mg", "tier_3",
        lambda: features["caffeine_amount_mean_mg"],
        config.default_caffeine_amount_mg,
    )

    jetlag = day_values("social_jetlag_minutes")
    features["social_jetlag_mean_minutes"] = resolve_flat(
        jetlag, flat_mean, "social_jetlag_mean_minutes", "tier_2",
        lambda: _personal_history_numeric_mean(session, participant_id, window_start, DailyObservation.social_jetlag_minutes),
        config.default_social_jetlag_minutes,
    )
    features["social_jetlag_recency_weighted_minutes"] = resolve_flat(
        jetlag, recency_weighted_mean, "social_jetlag_recency_weighted_minutes", "tier_2",
        lambda: features["social_jetlag_mean_minutes"],
        config.default_social_jetlag_minutes,
    )

    free_day_flags = day_values("is_free_day")
    known_flags = [v for v in free_day_flags if v is not None]
    free_ratio = ratio(sum(1 for v in known_flags if v), len(known_flags))
    features["free_day_ratio"] = resolve_flat(
        [free_ratio], lambda vs: vs[0], "free_day_ratio", "tier_1",
        lambda: _personal_history_free_day_ratio(session, participant_id, window_start),
        config.default_free_day_ratio,
    )


def _hours(minutes: Optional[float]) -> Optional[float]:
    return minutes / 60.0 if minutes is not None else None
