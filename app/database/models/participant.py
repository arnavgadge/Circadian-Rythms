"""Participant identity and stable/current-state profile tables."""

from __future__ import annotations

from datetime import date, time
from typing import Optional

from sqlalchemy import Date, Float, ForeignKey, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, PortableJSON, TimestampMixin


class Participant(Base, TimestampMixin):
    """A single enrolled participant: identity/onboarding metadata only.

    Biological characteristics and computed current state live in
    :class:`ParticipantProfile`, kept separate so identity data is not
    mixed with the fields the computational pipeline updates.
    """

    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    enrollment_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    onboarding_completed_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    profile: Mapped[Optional["ParticipantProfile"]] = relationship(
        back_populates="participant", uselist=False, cascade="all, delete-orphan"
    )


class ParticipantProfile(Base, TimestampMixin):
    """Stable biological traits plus the participant's current computed state.

    ``intrinsic_dlmo_time`` is the stable biological predisposition,
    ``adapted_dlmo_time`` is the slowly-changing behavioral equilibrium,
    and ``current_dlmo_time`` is the latest dynamic daily estimate --
    three distinct concepts that must not be collapsed into one field.
    The chronotype category shown to the user is the intrinsic
    category, not a value derived from the dynamic state.

    This table holds current/mutable state only; the immutable
    per-day prediction history lives in
    :class:`~app.database.models.circadian.CircadianLabel`.
    """

    __tablename__ = "participant_profiles"

    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), primary_key=True
    )

    chronotype_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    intrinsic_dlmo_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    adapted_dlmo_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    current_dlmo_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    current_dlmo_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    meq_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    meq_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    msfsc_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)

    current_alignment_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_alignment_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    synthetic_personality_profile: Mapped[Optional[dict]] = mapped_column(
        PortableJSON, nullable=True
    )

    participant: Mapped["Participant"] = relationship(back_populates="profile")
