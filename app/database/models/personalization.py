"""Learned personalization state.

``PersonalEffectModel`` and ``BanditState`` both represent current,
mutable learned state -- one row per participant/intervention type,
updated in place as more observations arrive. The model-fitting and
Thompson-sampling algorithms themselves belong to a later phase; this
module only defines where their state is stored.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class PersonalEffectModel(Base):
    """Current learned linear intervention-effect model for one participant/type."""

    __tablename__ = "personal_effect_models"
    __table_args__ = (
        UniqueConstraint(
            "participant_id", "intervention_type", name="uq_effect_model_participant_type"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    intervention_type: Mapped[str] = mapped_column(String(50), nullable=False)

    slope: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    intercept: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    r_squared: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    num_observations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    personalization_phase: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # Added by Phase 13 (migration bd2e1f4a9c31): the model-validity /
    # explainability metadata the personalization engine needs
    # alongside the coefficients themselves. Historical evolution of
    # an estimate is not versioned in *this* row (it is a current-state
    # table, mirroring participant_profiles) -- the auditable history
    # lives in Phase 12's immutable intervention_effect_estimates,
    # which this row's evidence_source/model_version point back to.
    confidence_interval_lower: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence_interval_upper: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    evidence_source: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class BanditState(Base):
    """Current contextual-bandit posterior state for one participant/type."""

    __tablename__ = "bandit_state"
    __table_args__ = (
        UniqueConstraint(
            "participant_id", "intervention_type", name="uq_bandit_state_participant_type"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    intervention_type: Mapped[str] = mapped_column(String(50), nullable=False)

    posterior_mean: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    posterior_variance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_pulls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_reward: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
