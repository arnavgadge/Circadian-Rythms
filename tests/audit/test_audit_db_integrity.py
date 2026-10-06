"""AUDIT 1 -- Database integrity (Phase 17 adversarial audit).

Covers, beyond what tests/test_db_schema.py, tests/test_db_constraints.py
and tests/test_db_longitudinal.py already exercise:

- Alembic migration-chain reproducibility against a fresh SQLite database
  (the "does `alembic upgrade head` alone produce the real schema" check
  scripts/init_db.py relies on -- test fixtures instead use
  Base.metadata.create_all() directly, so this path was previously
  untested).
- Broad participant-delete cascade across every FK-bearing table, not
  just the two tables the existing longitudinal test checks.
- Full-transaction rollback: a forced exception at the *last* write step
  must leave zero rows in *every* table touched earlier in the same
  transaction (not just the headline CircadianLabel row).
- The idempotency guarantee under a naive double invocation, including
  the specific DB-level invariant ("at most one is_latest=True row per
  participant/date") the application logic relies on -- and a documented
  finding about what backs that invariant.
"""

from __future__ import annotations

import os
from datetime import date

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    AlignmentResult,
    BanditState,
    Base,
    CircadianLabel,
    ContributorResult,
    DailyObservation,
    InterventionEffectEstimate,
    InterventionLog,
    MissingDataEvent,
    Participant,
    ParticipantProfile,
    PersonalEffectModel,
    PhysiologyLog,
    Recommendation,
    SafetyFlag,
)
from app.database.seed import seed_reference_data
from app.pipeline import orchestrator as orchestrator_module
from app.pipeline.orchestrator import run_daily_inference
from app.pipeline.types import SUCCESS


# --------------------------------------------------------------------------
# Migration reproducibility
# --------------------------------------------------------------------------


def test_alembic_upgrade_head_produces_the_same_tables_as_the_orm_metadata(tmp_path, monkeypatch):
    """`alembic upgrade head` against a brand-new SQLite file (exactly the
    path scripts/init_db.py takes) must create every table declared in
    app.database.models -- the migration chain must not have drifted
    from the ORM models it is supposed to mirror."""

    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "alembic_head.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("CIRCADIANIQ_DATABASE_URL", db_url)
    monkeypatch.setenv("CIRCADIANIQ_ENV", "testing")

    project_root = os.getcwd()
    alembic_cfg = Config(str(f"{project_root}/alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(f"{project_root}/migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url, future=True)
    inspector = inspect(engine)
    migrated_tables = set(inspector.get_table_names()) - {"alembic_version"}
    orm_tables = set(Base.metadata.tables.keys())

    missing_from_migrations = orm_tables - migrated_tables
    assert not missing_from_migrations, (
        f"Tables declared in app.database.models but not produced by "
        f"`alembic upgrade head`: {missing_from_migrations}"
    )
    engine.dispose()


def test_alembic_upgrade_head_is_reproducible_across_two_fresh_databases(tmp_path, monkeypatch):
    """Running the same migration chain against two independent fresh
    SQLite files must produce structurally identical schemas (same
    tables, same columns per table)."""

    from alembic import command
    from alembic.config import Config

    project_root = os.getcwd()
    schemas = []
    for name in ("a.db", "b.db"):
        db_path = tmp_path / name
        db_url = f"sqlite:///{db_path}"
        alembic_cfg = Config(str(f"{project_root}/alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(f"{project_root}/migrations"))
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(alembic_cfg, "head")

        engine = create_engine(db_url, future=True)
        inspector = inspect(engine)
        schema = {
            table: sorted(col["name"] for col in inspector.get_columns(table))
            for table in inspector.get_table_names()
            if table != "alembic_version"
        }
        schemas.append(schema)
        engine.dispose()

    assert schemas[0] == schemas[1]


def test_alembic_upgrade_head_in_process_does_not_disable_application_loggers(tmp_path):
    """Regression: migrations/env.py's ``fileConfig(...)`` call used to
    run with its default ``disable_existing_loggers=True``, which
    silently and *persistently* disables (``logger.disabled = True``,
    an attribute that survives across pytest tests within the same
    process, unlike handler attachment which pytest's caplog plugin
    resets per test) every logger already created in this process --
    e.g. ``app.pipeline.orchestrator``'s -- that isn't explicitly
    listed in alembic.ini's [loggers] section. Since scripts/init_db.py
    runs Alembic in-process (not via a subprocess), this would
    permanently kill the application's own error logging for the rest
    of any process that both uses app loggers and later runs a
    migration -- exactly what an earlier ordering of this test file
    did to tests/audit/test_audit_failure_injection.py (its
    ``caplog.records`` assertions all silently came back empty)."""

    import logging

    from alembic import command
    from alembic.config import Config

    orchestrator_logger = logging.getLogger("app.pipeline.orchestrator")
    orchestrator_logger.disabled = False  # in case an earlier test left it disabled

    project_root = os.getcwd()
    db_path = tmp_path / "logger_check.db"
    alembic_cfg = Config(str(f"{project_root}/alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(f"{project_root}/migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(alembic_cfg, "head")

    assert not orchestrator_logger.disabled, (
        "alembic upgrade head (run in-process) disabled app.pipeline.orchestrator's logger -- "
        "migrations/env.py's fileConfig() call is missing disable_existing_loggers=False"
    )


# --------------------------------------------------------------------------
# Cascade delete across every FK-bearing table
# --------------------------------------------------------------------------


def test_deleting_a_participant_cascades_across_all_owned_tables(db_session_factory):
    """Every table that carries participant_id as an ownership FK must be
    orphan-free after the owning participant is deleted -- not just the
    two tables tests/test_db_longitudinal.py already checks."""

    session = db_session_factory()
    participant = Participant(participant_code="CASCADE01", enrollment_date=date(2026, 1, 1))
    session.add(participant)
    session.commit()
    pid = participant.id

    session.add(ParticipantProfile(participant_id=pid, chronotype_category="intermediate"))
    session.add(DailyObservation(participant_id=pid, observation_date=date(2026, 1, 1)))
    session.add(PhysiologyLog(participant_id=pid, observation_date=date(2026, 1, 1)))
    label = CircadianLabel(participant_id=pid, target_date=date(2026, 1, 1), prediction_status="success")
    session.add(label)
    session.commit()

    session.add(
        AlignmentResult(
            circadian_label_id=label.id,
            participant_id=pid,
            target_date=date(2026, 1, 1),
            final_alignment_score=50.0,
            phase_alignment_score=50.0,
            behavioral_alignment_score=50.0,
        )
    )
    session.commit()
    alignment = session.execute(select(AlignmentResult).where(AlignmentResult.circadian_label_id == label.id)).scalar_one()
    session.add(
        ContributorResult(
            alignment_result_id=alignment.id,
            participant_id=pid,
            target_date=date(2026, 1, 1),
            rank=1,
            contributor_signal="sleep_consistency",
        )
    )
    session.add(SafetyFlag(participant_id=pid, flagged_date=date(2026, 1, 1), flag_type="continuous_dlmo_drift"))
    session.add(PersonalEffectModel(participant_id=pid, intervention_type="light"))
    session.add(BanditState(participant_id=pid, intervention_type="light"))
    session.add(MissingDataEvent(participant_id=pid, observation_date=date(2026, 1, 1), signal_name="sleep_onset", is_missing=True))

    rec = Recommendation(intervention_code="CASC_REC", intervention_type="light", title="t")
    session.add(rec)
    session.commit()
    session.add(InterventionLog(participant_id=pid, recommendation_id=rec.id, log_date=date(2026, 1, 1)))
    session.add(
        InterventionEffectEstimate(
            participant_id=pid, recommendation_id=rec.id, measurement_phase=1,
            interpretation="insufficient_data", methodology_version="1.0.0",
        )
    )
    session.commit()

    session.delete(participant)
    session.commit()

    owned_tables = [
        (ParticipantProfile, ParticipantProfile.participant_id),
        (DailyObservation, DailyObservation.participant_id),
        (PhysiologyLog, PhysiologyLog.participant_id),
        (CircadianLabel, CircadianLabel.participant_id),
        (AlignmentResult, AlignmentResult.participant_id),
        (ContributorResult, ContributorResult.participant_id),
        (SafetyFlag, SafetyFlag.participant_id),
        (PersonalEffectModel, PersonalEffectModel.participant_id),
        (BanditState, BanditState.participant_id),
        (MissingDataEvent, MissingDataEvent.participant_id),
        (InterventionLog, InterventionLog.participant_id),
        (InterventionEffectEstimate, InterventionEffectEstimate.participant_id),
    ]
    for model, column in owned_tables:
        remaining = session.execute(select(model).where(column == pid)).scalars().all()
        assert remaining == [], f"{model.__tablename__} left {len(remaining)} orphan row(s) after participant delete"

    # The shared catalogue row itself must survive (it is not owned by
    # the participant), only the participant's own log referencing it.
    assert session.get(Recommendation, rec.id) is not None
    session.close()


# --------------------------------------------------------------------------
# Transaction rollback leaves no partial row
# --------------------------------------------------------------------------


def test_forced_failure_at_final_write_step_leaves_no_partial_row_in_any_table(pipeline_session_factory, monkeypatch):
    """Force an exception in the very last statement of the pipeline's
    single write transaction (update_participant_state). Everything
    written earlier in that same transaction -- the CircadianLabel, its
    AlignmentResult, and its ContributorResult rows -- must not survive
    either: the whole transaction must roll back as one unit, not just
    the field that happened to fail."""

    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    target_date = dates[6]

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated failure in the last write step")

    monkeypatch.setattr(orchestrator_module, "update_participant_state", _boom)
    result = run_daily_inference(pid, target_date, pipeline_session_factory)
    assert result.status == "FAILED"
    assert result.persistence_status == "not_attempted"

    session = pipeline_session_factory()
    try:
        labels = session.execute(
            select(CircadianLabel).where(
                CircadianLabel.participant_id == pid,
                CircadianLabel.target_date == target_date,
                CircadianLabel.prediction_status.in_(("success", "insufficient_history", "no_prediction")),
            )
        ).scalars().all()
        assert labels == [], "CircadianLabel row survived a rolled-back transaction"

        alignments = session.execute(
            select(AlignmentResult).where(
                AlignmentResult.participant_id == pid, AlignmentResult.target_date == target_date
            )
        ).scalars().all()
        assert alignments == [], "AlignmentResult row survived a rolled-back transaction"

        contributors = session.execute(
            select(ContributorResult).where(
                ContributorResult.participant_id == pid, ContributorResult.target_date == target_date
            )
        ).scalars().all()
        assert contributors == [], "ContributorResult rows survived a rolled-back transaction"

        logs = session.execute(
            select(InterventionLog).where(
                InterventionLog.participant_id == pid, InterventionLog.log_date == target_date
            )
        ).scalars().all()
        assert logs == [], "InterventionLog row survived a rolled-back transaction"
    finally:
        session.close()


# --------------------------------------------------------------------------
# Idempotency under naive double-call
# --------------------------------------------------------------------------


def test_naive_double_call_never_leaves_more_than_one_is_latest_row(pipeline_session_factory):
    """The DB-level invariant the whole idempotency design depends on:
    at most one is_latest=True CircadianLabel row per participant/date,
    ever -- checked directly against the database, not just against the
    orchestrator's own return value."""

    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    target_date = dates[6]

    run_daily_inference(pid, target_date, pipeline_session_factory)
    run_daily_inference(pid, target_date, pipeline_session_factory)  # naive duplicate call

    session = pipeline_session_factory()
    try:
        latest_rows = session.execute(
            select(CircadianLabel).where(
                CircadianLabel.participant_id == pid,
                CircadianLabel.target_date == target_date,
                CircadianLabel.is_latest.is_(True),
            )
        ).scalars().all()
    finally:
        session.close()

    assert len(latest_rows) == 1


def test_forced_rerun_twice_never_leaves_more_than_one_is_latest_row(pipeline_session_factory):
    """Same invariant, exercised via the explicit versioned-rerun path
    (force_rerun=True) called twice back to back -- this is the path
    that actually calls supersede_existing_label, so it is the one
    that would reveal a lost-update race if the DB schema did not
    happen to make writes serialize."""

    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    target_date = dates[6]

    run_daily_inference(pid, target_date, pipeline_session_factory, force_rerun=True)
    run_daily_inference(pid, target_date, pipeline_session_factory, force_rerun=True)

    session = pipeline_session_factory()
    try:
        latest_rows = session.execute(
            select(CircadianLabel).where(
                CircadianLabel.participant_id == pid,
                CircadianLabel.target_date == target_date,
                CircadianLabel.is_latest.is_(True),
            )
        ).scalars().all()
        all_rows = session.execute(
            select(CircadianLabel).where(
                CircadianLabel.participant_id == pid, CircadianLabel.target_date == target_date
            )
        ).scalars().all()
    finally:
        session.close()

    assert len(latest_rows) == 1
    # Two explicit reruns plus the Phase 3 synthetic seed row for this date.
    assert len(all_rows) >= 3


def test_no_db_level_constraint_enforces_at_most_one_is_latest_row(db_session_factory):
    """FINDING (documented, not fixed -- see audit report): there is no
    partial-unique index or CHECK constraint on circadian_labels
    enforcing "at most one is_latest=True row per (participant_id,
    target_date)" at the database level. The invariant currently holds
    only because application code (supersede_existing_label) always
    flips every existing is_latest=True row before inserting a new one,
    combined with SQLite's single-writer transaction serialization.
    This test documents that the schema *permits* the invalid state
    (two is_latest=True rows for the same participant/date) when
    written directly, i.e. the guarantee is enforced by pipeline
    discipline, not by the schema itself."""

    session = db_session_factory()
    participant = Participant(participant_code="NOCONSTRAINT", enrollment_date=date(2026, 1, 1))
    session.add(participant)
    session.commit()

    session.add(
        CircadianLabel(
            participant_id=participant.id, target_date=date(2026, 1, 1),
            prediction_status="success", is_latest=True,
        )
    )
    session.add(
        CircadianLabel(
            participant_id=participant.id, target_date=date(2026, 1, 1),
            prediction_status="success", is_latest=True,
        )
    )
    # No IntegrityError is raised: the schema has no constraint that
    # would prevent this. This is the finding -- not asserting failure.
    session.commit()

    rows = session.execute(
        select(CircadianLabel).where(
            CircadianLabel.participant_id == participant.id, CircadianLabel.is_latest.is_(True)
        )
    ).scalars().all()
    assert len(rows) == 2, (
        "Expected the schema to permit two is_latest=True rows (documenting the "
        "missing DB-level constraint); if this now fails, a constraint has been "
        "added and this test (and the audit finding) should be updated/removed."
    )
    session.close()


def _first_participant_id(session_factory) -> int:
    session = session_factory()
    try:
        return session.execute(select(Participant.id).order_by(Participant.id)).scalars().first()
    finally:
        session.close()


def _observation_dates(session_factory, pid: int) -> list:
    session = session_factory()
    try:
        return list(
            session.execute(
                select(DailyObservation.observation_date)
                .where(DailyObservation.participant_id == pid)
                .order_by(DailyObservation.observation_date)
            ).scalars().all()
        )
    finally:
        session.close()


@pytest.fixture
def pipeline_session_factory(db_session_factory, small_synthetic_dataset):
    session = db_session_factory()
    seed_reference_data(session)
    session.close()
    return db_session_factory
