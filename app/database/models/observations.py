"""Raw daily behavioral/environmental and physiological observations.

Behavioral signals used (now or later) by Version 1 feature engineering
live in :class:`DailyObservation`. Physiological signals live in a
separate :class:`PhysiologyLog` table so they are never silently
treated as Version 1 behavioral inputs.

Clock-time columns (``*_time``) preserve the original wall-clock value
for human display and downstream circular (sin/cos) encoding. Elapsed
durations that may cross midnight (e.g. a sleep onset just before
midnight and an offset just after) are captured separately as plain
numeric ``*_minutes`` columns computed by the application -- times and
durations are intentionally different column types and must not be
confused.
"""

from __future__ import annotations

from datetime import date, time
from typing import Optional

from sqlalchemy import Boolean, Date, Float, ForeignKey, Index, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, CreatedAtMixin


class DailyObservation(Base, CreatedAtMixin):
    """One row per participant per calendar date of raw behavioral inputs.

    Historical fact table, append-only in principle. Sleep, light,
    screen, meal, exercise, and caffeine fields all share the same
    grain (participant, date), so they are kept together here rather
    than split into near-duplicate single-purpose tables.
    """

    __tablename__ = "daily_observations"
    __table_args__ = (
        UniqueConstraint(
            "participant_id", "observation_date", name="uq_daily_obs_participant_date"
        ),
        Index("ix_daily_obs_participant_date", "participant_id", "observation_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    observation_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Sleep
    sleep_onset_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    sleep_offset_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    sleep_duration_minutes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sleep_midpoint_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    sleep_midpoint_variability_minutes: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    is_free_day: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    free_day_sleep_onset_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    free_day_sleep_offset_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    free_day_sleep_midpoint_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    social_jetlag_minutes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    free_day_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    msfsc_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)

    # Light
    morning_light_start_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    morning_light_duration_minutes: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )

    # Screen
    evening_screen_end_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    evening_screen_duration_minutes: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )

    # Meals
    last_meal_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    meal_to_sleep_gap_minutes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Exercise
    exercise_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    exercise_duration_minutes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Caffeine
    last_caffeine_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    caffeine_amount_mg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    participant: Mapped["Participant"] = relationship()


class PhysiologyLog(Base, CreatedAtMixin):
    """One row per participant per date of physiological measurements.

    Not used by the Version 1 ML model. Kept in its own table so it is
    never silently folded into Version 1 behavioral feature
    engineering.
    """

    __tablename__ = "physiology_logs"
    __table_args__ = (
        UniqueConstraint(
            "participant_id", "observation_date", name="uq_physiology_participant_date"
        ),
        Index("ix_physiology_participant_date", "participant_id", "observation_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    observation_date: Mapped[date] = mapped_column(Date, nullable=False)

    resting_heart_rate_bpm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hrv_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wrist_temperature_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    participant: Mapped["Participant"] = relationship()
