"""SQLAlchemy engine and session management.

This is the primary database interface for the relational schema
introduced in Phase 2. The lightweight ``DatabaseConnection`` /
``transaction`` primitives from Phase 1 (see
``app.database.connection`` / ``app.database.transaction``) remain
available for simple raw-SQL use, but ORM-backed code should use the
session machinery defined here.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import AppConfig


def create_app_engine(config: AppConfig) -> Engine:
    """Create a SQLAlchemy engine for the configured database URL.

    Enables foreign-key enforcement on SQLite connections, since
    SQLite disables it by default; PostgreSQL enforces foreign keys
    natively and needs no such hook.
    """

    engine = create_engine(config.database_url, future=True)

    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Build a session factory bound to the given engine."""

    return sessionmaker(bind=engine, future=True, expire_on_commit=False)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Run a block of ORM work as a single atomic transaction.

    Commits on success, rolls back if an exception is raised. This is
    the primitive later phases should use for the daily inference
    pipeline's read -> compute -> write transaction.
    """

    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
