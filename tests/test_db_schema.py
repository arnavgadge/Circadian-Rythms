"""Schema-level tests: creation, tables, primary keys, and indexes.

Uses an isolated in-memory SQLite engine per test via the ``engine``
fixture in ``conftest.py`` -- these tests never touch the on-disk
development database.
"""

from __future__ import annotations

from sqlalchemy import inspect

from app.database.init_db import create_all_tables
from app.database.models import Base

EXPECTED_TABLES = {
    "participants",
    "participant_profiles",
    "daily_observations",
    "physiology_logs",
    "circadian_labels",
    "alignment_results",
    "contributor_results",
    "recommendations",
    "intervention_log",
    "personal_effect_models",
    "bandit_state",
    "missing_data_events",
    "safety_flags",
    "training_runs",
}


def test_schema_creation_succeeds(engine):
    create_all_tables(engine)


def test_all_required_tables_exist(engine):
    create_all_tables(engine)
    inspector = inspect(engine)
    assert EXPECTED_TABLES.issubset(set(inspector.get_table_names()))


def test_every_table_has_a_primary_key(engine):
    create_all_tables(engine)
    inspector = inspect(engine)
    for table_name in EXPECTED_TABLES:
        pk = inspector.get_pk_constraint(table_name)
        assert pk["constrained_columns"], f"{table_name} has no primary key"


def test_expected_longitudinal_indexes_exist(engine):
    create_all_tables(engine)
    inspector = inspect(engine)

    expected_indexed_tables = {
        "daily_observations",
        "physiology_logs",
        "circadian_labels",
        "alignment_results",
        "contributor_results",
        "intervention_log",
        "missing_data_events",
        "safety_flags",
    }
    for table_name in expected_indexed_tables:
        index_columns = {
            tuple(ix["column_names"]) for ix in inspector.get_indexes(table_name)
        }
        assert any(
            cols and cols[0] == "participant_id" for cols in index_columns
        ), f"{table_name} has no participant-scoped index"


def test_base_metadata_matches_expected_table_set():
    assert EXPECTED_TABLES.issubset(set(Base.metadata.tables.keys()))
