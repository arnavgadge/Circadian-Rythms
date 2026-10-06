"""Safety flag events.

Detection logic (what triggers a flag, e.g. persistent late phase or
continuous drift) belongs to a later phase; this table only stores the
resulting flag. Raising a flag is an append-only historical fact;
``resolved_date``/``resolved_by`` are the only fields expected to be
mutated later, when the flag is resolved.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column


from app.database.models.base import Base, PortableJSON


class SafetyFlag(Base):
    __tablename__ = "safety_flags"
    __table_args__ = (
        Index("ix_safety_flags_participant_date", "participant_id", "flagged_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    flagged_date: Mapped[date] = mapped_column(Date, nullable=False)

    flag_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    message_shown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recommendation_suppressed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    resolved_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Added by Phase 14 (migration c3f7a08e21b4). ``message_key`` is the
    # structured lookup key (see app.safety.messages) that produced
    # ``message_shown``, so the exact wording can evolve without losing
    # traceability to which fixed message was actually displayed.
    # ``first_detected_date``/``last_observed_date`` bound the evidence
    # window this flag's episode has been open across; per this table's
    # own append-only contract (see module docstring), only
    # ``last_observed_date`` (alongside ``resolved_date``/``resolved_by``)
    # is ever mutated after creation -- ``first_detected_date``,
    # ``triggering_statistics`` and ``detection_version`` are fixed at
    # creation time, a permanent record of what first triggered the flag.
    message_key: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    first_detected_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_observed_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    triggering_statistics: Mapped[Optional[dict]] = mapped_column(PortableJSON, nullable=True)
    detection_version: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
