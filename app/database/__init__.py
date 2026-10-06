"""Database abstraction package.

Two layers coexist here:

- ``connection`` / ``transaction`` -- the lightweight, engine-agnostic
  raw-SQL primitives from Phase 1.
- ``engine`` / ``models`` / ``init_db`` / ``seed`` -- the SQLAlchemy
  ORM layer introduced in Phase 2, which defines and manages the full
  relational schema. This is the layer later phases should use for
  all schema-backed reads and writes; see
  ``docs/database_architecture.md`` for the full design.
"""

from app.database.connection import DatabaseConnection, create_connection
from app.database.engine import create_app_engine, create_session_factory, session_scope
from app.database.init_db import create_all_tables
from app.database.transaction import transaction

__all__ = [
    "DatabaseConnection",
    "create_connection",
    "transaction",
    "create_app_engine",
    "create_session_factory",
    "session_scope",
    "create_all_tables",
]
