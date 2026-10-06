"""Model training run metadata.

Training itself happens in a later, offline phase; this table only
stores the resulting record so predictions can be traced back to the
model version that produced them (see
``CircadianLabel.training_run_id``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base, PortableJSON


class TrainingRun(Base):
    __tablename__ = "training_runs"
    __table_args__ = (
        UniqueConstraint("model_type", "model_version", name="uq_training_run_type_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    num_participants: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    num_windows: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    feature_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cv_metrics: Mapped[Optional[dict]] = mapped_column(PortableJSON, nullable=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    artifact_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    artifact_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
