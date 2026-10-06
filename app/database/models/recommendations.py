"""Intervention catalogue and the longitudinal intervention log.

``Recommendation`` is the candidate-intervention catalogue -- the
source of truth for which interventions exist -- not the
selection algorithm. ``InterventionLog`` is the append-only historical
record of what was actually recommended to a participant and its
observed outcome.
"""

from __future__ import annotations

from datetime import date, time
from typing import Optional

from sqlalchemy import Boolean, Date, Float, ForeignKey, Index, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, CreatedAtMixin, PortableJSON, TimestampMixin


class Recommendation(Base, TimestampMixin):
    """A candidate intervention in the recommendation catalogue.

    ``literature_expected_improvement_minutes`` is intentionally left
    for later phases to populate from cited literature -- no effect
    size is fabricated here.
    """

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    intervention_code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    intervention_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_behavior: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    literature_expected_improvement_minutes: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    feasibility_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[Optional[dict]] = mapped_column(PortableJSON, nullable=True)


class InterventionLog(Base, CreatedAtMixin):
    """Append-only record of one intervention issued to a participant on a date.

    The exact intervention-effect algorithms (compliance scoring,
    effect estimation, confound detection) belong to later phases;
    this table only stores their inputs and outputs.
    """

    __tablename__ = "intervention_log"
    __table_args__ = (
        Index("ix_intervention_log_participant_date", "participant_id", "log_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("recommendations.id", ondelete="RESTRICT"), nullable=False
    )
    log_date: Mapped[date] = mapped_column(Date, nullable=False)

    recommendation_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Target/actual may be a clock time (e.g. "move light exposure to 7:00")
    # or a plain magnitude (e.g. a duration); both are supported.
    target_value_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    target_value_numeric: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    actual_value_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    actual_value_numeric: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    expected_improvement_minutes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    personalization_phase: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    compliance_binary: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    compliance_degree: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    dlmo_before_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    dlmo_after_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    dlmo_change_minutes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    alignment_before: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    alignment_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    alignment_change: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    measurement_phase: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    effect_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confound_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    recommendation: Mapped["Recommendation"] = relationship()
