"""Shared ORM base, mixins, and portable column types for the CircadianIQ schema."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Declarative base shared by every CircadianIQ ORM model."""


PortableJSON = JSON().with_variant(JSONB, "postgresql")
"""JSON column type: generic JSON on SQLite, native JSONB on PostgreSQL.

Reserved for genuinely variable/explanatory structures (e.g. alignment
component snapshots, missing-feature lists, training-run CV metrics)
-- not a substitute for relational columns on data that needs to be
queried directly.
"""


class CreatedAtMixin:
    """Adds an immutable ``created_at`` audit column.

    Use on append-only / historical-fact tables whose rows are written
    once and never updated in place.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TimestampMixin(CreatedAtMixin):
    """Adds ``created_at`` and ``updated_at`` audit columns.

    Use on mutable "current state" tables whose rows are updated in
    place as new information arrives.
    """

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
