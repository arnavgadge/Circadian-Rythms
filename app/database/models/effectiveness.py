"""Versioned intervention-effect estimates (Phase 12).

``intervention_log`` (Phase 10/11) already stores the day-by-day
recommendation/compliance facts; this table stores the **derived,
evolving estimate** computed from those facts -- kept separate because
an estimate has its own lifecycle (it is recomputed as more history
accumulates, and old estimates must remain auditable rather than being
overwritten) that does not belong on the per-day fact table.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base, PortableJSON


class InterventionEffectEstimate(Base):
    """One immutable effect-estimate computation for one participant/
    intervention. A recomputation (more history, a new methodology
    version) inserts a new row rather than overwriting the previous
    estimate -- see ``docs/intervention_effectiveness.md``
    "Recomputation"."""

    __tablename__ = "intervention_effect_estimates"
    __table_args__ = (
        Index("ix_effect_estimates_participant_intervention", "participant_id", "recommendation_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("recommendations.id", ondelete="CASCADE"), nullable=False
    )

    measurement_phase: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, or 3
    interpretation: Mapped[str] = mapped_column(String(30), nullable=False)  # see app.effectiveness.config

    period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    effect_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # minutes, signed (advance negative)
    confidence_interval_lower: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence_interval_upper: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    standard_error: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    r_squared: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    n_observations: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    compliance_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confound_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    methodology_version: Mapped[str] = mapped_column(String(30), nullable=False)
    model_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    diagnostics: Mapped[Optional[dict]] = mapped_column(PortableJSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
