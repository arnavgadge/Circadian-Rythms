"""Tests for the database abstraction layer."""

import pytest

from app.database.connection import (
    PostgreSQLConnection,
    SQLiteConnection,
    create_connection,
)
from app.database.transaction import transaction


def test_create_connection_returns_sqlite_for_sqlite_url(tmp_path):
    db_path = tmp_path / "test.db"
    conn = create_connection(f"sqlite:///{db_path}")
    assert isinstance(conn, SQLiteConnection)


def test_create_connection_returns_postgres_for_postgres_url():
    conn = create_connection("postgresql://user:pass@localhost:5432/db")
    assert isinstance(conn, PostgreSQLConnection)


def test_create_connection_rejects_unsupported_scheme():
    with pytest.raises(ValueError):
        create_connection("mysql://localhost/db")


def test_sqlite_connection_connect_and_close(tmp_path):
    db_path = tmp_path / "test.db"
    conn = SQLiteConnection(str(db_path))

    conn.connect()
    assert conn.raw_connection is not None

    conn.close()
    assert conn.raw_connection is None


def test_sqlite_connection_execute_requires_open_connection(tmp_path):
    db_path = tmp_path / "test.db"
    conn = SQLiteConnection(str(db_path))

    with pytest.raises(RuntimeError):
        conn.execute("SELECT 1")


def test_transaction_commits_on_success(tmp_path):
    db_path = tmp_path / "test.db"
    conn = SQLiteConnection(str(db_path))
    conn.connect()
    conn.execute("CREATE TABLE example (id INTEGER)")

    with transaction(conn):
        conn.execute("INSERT INTO example (id) VALUES (1)")

    cursor = conn.execute("SELECT COUNT(*) FROM example")
    assert cursor.fetchone()[0] == 1
    conn.close()


def test_transaction_rolls_back_on_error(tmp_path):
    db_path = tmp_path / "test.db"
    conn = SQLiteConnection(str(db_path))
    conn.connect()
    conn.execute("CREATE TABLE example (id INTEGER)")
    conn.raw_connection.commit()

    with pytest.raises(RuntimeError):
        with transaction(conn):
            conn.execute("INSERT INTO example (id) VALUES (1)")
            raise RuntimeError("boom")

    cursor = conn.execute("SELECT COUNT(*) FROM example")
    assert cursor.fetchone()[0] == 0
    conn.close()


def test_transaction_requires_open_connection(tmp_path):
    db_path = tmp_path / "test.db"
    conn = SQLiteConnection(str(db_path))

    with pytest.raises(RuntimeError):
        with transaction(conn):
            pass
