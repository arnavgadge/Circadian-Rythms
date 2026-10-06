"""Transaction handling for database connections."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from app.database.connection import DatabaseConnection


@contextmanager
def transaction(connection: DatabaseConnection) -> Iterator[DatabaseConnection]:
    """Run a block of work as a single atomic transaction.

    Commits when the block completes successfully; rolls back and
    re-raises if the block raises an exception. The connection must
    already be open before entering this context.
    """

    raw = connection.raw_connection
    if raw is None:
        raise RuntimeError("Connection must be open before starting a transaction.")

    try:
        yield connection
        raw.commit()
    except Exception:
        raw.rollback()
        raise
