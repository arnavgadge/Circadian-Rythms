"""Circadian phase prediction, alignment, and contributor result tables.

These three tables form one conceptual "circadian result" per
prediction event, split for normalization:

- :class:`CircadianLabel` -- the phase prediction itself.
- :class:`AlignmentResult` -- the 1:1 alignment score breakdown.
- :class:`ContributorResult` -- the ranked contributor rows (many per
  alignment result).

``CircadianLabel`` rows are immutable history: re-running a prediction
for an already-predicted date inserts a new row rather than
overwriting the old one. ``is_latest`` is the one intentionally
mutable pointer field, flipped to ``False`` on a superseded row when a
newer prediction for the same date is written.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, PortableJSON


class CircadianLabel(Base):
    """One immutable circadian phase prediction event for a participant/date.

    Stores the raw model outputs (including the sin/cos encoding used
    internally) alongside the decoded, human-interpretable clock time
    for each stage, since the sin/cos representation alone is not
    sufficient for display.
    """

    __tablename__ = "circadian_labels"
    __table_args__ = (
        Index("ix_circadian_labels_participant_date", "participant_id", "target_date"),
        Index("ix_circadian_labels_participant_latest", "participant_id", "is_latest"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    is_latest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    prediction_status: Mapped[str] = mapped_column(String(30), nullable=False)

    # Raw ML model output (sin/cos encoding) plus its decoded clock time.
    xgboost_dlmo_sin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    xgboost_dlmo_cos: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    xgboost_dlmo_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)

    # State-model prediction.
    state_model_dlmo_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)

    # Fused result: raw sin/cos plus the decoded, user-facing clock time.
    fused_dlmo_sin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fused_dlmo_cos: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fused_dlmo_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)

    disagreement_minutes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    disagreement_regime: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence_label: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    data_completeness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    missing_features: Mapped[Optional[list]] = mapped_column(PortableJSON, nullable=True)
    imputed_features: Mapped[Optional[list]] = mapped_column(PortableJSON, nullable=True)

    training_run_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("training_runs.id", ondelete="SET NULL"), nullable=True
    )

    # Added by Phase 14 (migration c3f7a08e21b4): the safety layer's own
    # decision for this prediction event, stored alongside it purely for
    # convenient joinless reads -- app.safety never derives these from
    # anything but safety_flags plus this same row's own confidence
    # fields, and never mutates fused_dlmo_sin/cos/time or any other
    # prediction field on this row.
    safe_output_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    recommendation_suppressed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    safety_severity: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    alignment_result: Mapped[Optional["AlignmentResult"]] = relationship(
        back_populates="circadian_label", uselist=False
    )


class AlignmentResult(Base):
    """Alignment score breakdown for one :class:`CircadianLabel` event.

    Final alignment score = 60% phase alignment + 40% behavioral
    alignment; that weighting is applied by the Python alignment
    engine in a later phase. This table stores the resulting
    components so the breakdown remains queryable rather than
    collapsed into a single number.
    """

    __tablename__ = "alignment_results"
    __table_args__ = (
        Index("ix_alignment_results_participant_date", "participant_id", "target_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    circadian_label_id: Mapped[int] = mapped_column(
        ForeignKey("circadian_labels.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    target_date: Mapped[date] = mapped_column(Date, nullable=False)

    final_alignment_score: Mapped[float] = mapped_column(Float, nullable=False)
    phase_alignment_score: Mapped[float] = mapped_column(Float, nullable=False)
    behavioral_alignment_score: Mapped[float] = mapped_column(Float, nullable=False)

    sleep_consistency_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    morning_light_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evening_screen_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    meal_timing_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    social_jetlag_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Added by Phase 16 (migration e5f9c27b4d8a): Phase 8's AlignmentResult
    # dataclass already carries both of these (derived from the fused
    # DLMO plus the configured phase-to-sleep offset, and the most
    # recently observed sleep onset); Phase 11's original persistence
    # simply did not store them. Needed for the UI's clock visualization
    # (estimated clock vs. ideal vs. actual sleep onset) without
    # recomputing anything in the frontend.
    ideal_sleep_onset_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    actual_sleep_onset_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)

    component_snapshot: Mapped[Optional[dict]] = mapped_column(PortableJSON, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    circadian_label: Mapped["CircadianLabel"] = relationship(back_populates="alignment_result")
    contributors: Mapped[list["ContributorResult"]] = relationship(
        back_populates="alignment_result", cascade="all, delete-orphan"
    )


class ContributorResult(Base):
    """One ranked contributor signal for an :class:`AlignmentResult`.

    Normalized (one row per rank) rather than a single unstructured
    string, so the top-N contributors remain independently queryable.
    """

    __tablename__ = "contributor_results"
    __table_args__ = (
        UniqueConstraint(
            "alignment_result_id", "rank", name="uq_contributor_alignment_rank"
        ),
        Index("ix_contributor_results_participant_date", "participant_id", "target_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    alignment_result_id: Mapped[int] = mapped_column(
        ForeignKey("alignment_results.id", ondelete="CASCADE"), nullable=False
    )
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    target_date: Mapped[date] = mapped_column(Date, nullable=False)

    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    contributor_signal: Mapped[str] = mapped_column(String(50), nullable=False)
    effect_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    alignment_deficit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    direction: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    anomaly_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # Added by Phase 15 (migration d4e8b19f3a2c): Phase 9 already computes
    # both of these (Contributor.contributor_score / .today_anomaly),
    # but Phase 11's original persistence did not store them; the API
    # layer needs them for a complete read-only contributors response,
    # so they are added here rather than recomputed at read time.
    contributor_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    today_anomaly: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    alignment_result: Mapped["AlignmentResult"] = relationship(back_populates="contributors")
