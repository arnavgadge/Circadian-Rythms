"""Database initialization.

For real deployments, schema changes should go through Alembic
migrations (see ``migrations/`` and ``alembic.ini``) so existing data
is preserved across schema changes. ``create_all_tables`` here is a
convenience path for tests and for fresh local/course-project
databases where there is no existing data to migrate.
"""

from __future__ import annotations

from sqlalchemy import Engine

from app.database.models import Base


def create_all_tables(engine: Engine) -> None:
    """Create every table registered on ``Base.metadata`` if not already present."""

    Base.metadata.create_all(engine)
