"""Missing-data / imputation audit trail.

Records, per participant/date/signal, whether a value was missing and
whether it was imputed. The tiering (critical/important/supporting)
and the imputation algorithm itself belong to a later phase; this
table only stores the outcome for auditability.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class MissingDataEvent(Base):
    """One audit row for one signal on one participant/date."""

    __tablename__ = "missing_data_events"
    __table_args__ = (
        Index("ix_missing_data_participant_date", "participant_id", "observation_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    circadian_label_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("circadian_labels.id", ondelete="SET NULL"), nullable=True
    )
    observation_date: Mapped[date] = mapped_column(Date, nullable=False)

    signal_name: Mapped[str] = mapped_column(String(50), nullable=False)
    signal_tier: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    is_missing: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_imputed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    imputation_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    confidence_penalty: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
