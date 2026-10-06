"""Database connection abstraction.

Provides a thin, engine-agnostic wrapper so the rest of the
application is not coupled to a specific database engine. Schema
design and repository/data-access classes are introduced in a later
phase.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from typing import Any, Optional
from urllib.parse import urlparse


class DatabaseConnection(ABC):
    """Engine-agnostic connection contract."""

    @abstractmethod
    def connect(self) -> None:
        """Open the underlying connection."""

    @abstractmethod
    def close(self) -> None:
        """Close the underlying connection, if open."""

    @abstractmethod
    def execute(self, query: str, params: tuple = ()) -> Any:
        """Execute a statement against the underlying connection."""

    @property
    @abstractmethod
    def raw_connection(self) -> Any:
        """The underlying driver connection object, or ``None`` if closed."""


class SQLiteConnection(DatabaseConnection):
    """SQLite-backed connection, used for local/course-project development."""

    def __init__(self, database_path: str) -> None:
        self._database_path = database_path
        self._connection: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        if self._connection is None:
            self._connection = sqlite3.connect(self._database_path)

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        if self._connection is None:
            raise RuntimeError("Connection is not open. Call connect() first.")
        return self._connection.execute(query, params)

    @property
    def raw_connection(self) -> Optional[sqlite3.Connection]:
        return self._connection


class PostgreSQLConnection(DatabaseConnection):
    """PostgreSQL-backed connection placeholder for future deployment.

    The driver dependency (e.g. ``psycopg``) is intentionally not added
    until a later phase actually requires connecting to PostgreSQL.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._connection: Optional[Any] = None

    def connect(self) -> None:
        raise NotImplementedError(
            "PostgreSQL support is scaffolded but not implemented in Phase 1."
        )

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def execute(self, query: str, params: tuple = ()) -> Any:
        raise NotImplementedError(
            "PostgreSQL support is scaffolded but not implemented in Phase 1."
        )

    @property
    def raw_connection(self) -> Optional[Any]:
        return self._connection


def create_connection(database_url: str) -> DatabaseConnection:
    """Factory that returns the correct :class:`DatabaseConnection` for a URL.

    Supports ``sqlite:///path/to/file.db`` and ``postgresql://...`` /
    ``postgres://...`` schemes.
    """

    parsed = urlparse(database_url)
    scheme = parsed.scheme.lower()

    if scheme == "sqlite":
        path = (
            database_url[len("sqlite:///") :]
            if database_url.startswith("sqlite:///")
            else parsed.path
        )
        return SQLiteConnection(path)

    if scheme in ("postgresql", "postgres"):
        return PostgreSQLConnection(database_url)

    raise ValueError(f"Unsupported database URL scheme: '{scheme}'")
