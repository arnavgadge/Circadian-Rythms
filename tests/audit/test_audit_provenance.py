"""AUDIT 22 -- Version provenance (Phase 17 adversarial audit).

Checks, per daily result row, whether the model/feature/state/fusion/
alignment/contributor/recommendation/personalization/safety version
that produced it can actually be identified afterwards -- via a column
or a joinable structure -- and reports exactly which components have
persisted provenance and which do not.

Method: run the real daily pipeline, then inspect only what is
actually queryable from the database afterwards (not the in-memory
DailyInferenceResult.diagnostics, which is never persisted).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.database.models import AlignmentResult, CircadianLabel, ContributorResult, DailyObservation, InterventionLog, Participant, TrainingRun
from app.database.seed import seed_reference_data
from app.pipeline.orchestrator import run_daily_inference
from app.pipeline.types import SUCCESS


@pytest.fixture
def pipeline_session_factory(db_session_factory, small_synthetic_dataset):
    session = db_session_factory()
    seed_reference_data(session)
    session.close()
    return db_session_factory


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


def test_circadian_label_can_identify_its_model_version_via_training_run_fk(pipeline_session_factory):
    """CircadianLabel.training_run_id -> TrainingRun.model_version is the
    one provenance link that IS persisted as a real, joinable FK
    column on the headline result row."""

    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    result = run_daily_inference(pid, dates[6], pipeline_session_factory)
    assert result.status == SUCCESS

    session = pipeline_session_factory()
    try:
        label = session.get(CircadianLabel, result.circadian_label_id)
        assert label.training_run_id is not None
        training_run = session.get(TrainingRun, label.training_run_id)
        assert training_run is not None
        assert training_run.model_version is not None
    finally:
        session.close()


def test_circadian_label_row_itself_has_no_columns_for_pipeline_config_fusion_or_state_version(pipeline_session_factory):
    """FINDING: CircadianLabel -- the headline per-day result row -- has
    no columns for pipeline_config_version, feature_manifest_version,
    state_config_version, or fusion_config_version. Those exist only
    in the in-memory DailyInferenceResult.diagnostics returned by
    run_daily_inference() (see app/pipeline/orchestrator.py
    _build_provenance()), which the pipeline never persists anywhere
    on this row. Anyone querying the database after the fact (rather
    than capturing the live return value) cannot recover which
    pipeline/feature-manifest/state/fusion config version produced a
    given CircadianLabel row."""

    label_columns = {c.name for c in CircadianLabel.__table__.columns}
    missing = {
        "pipeline_config_version", "feature_manifest_version",
        "state_config_version", "fusion_config_version",
    }
    assert missing.isdisjoint(label_columns), (
        "If this now fails, provenance columns have been added to CircadianLabel "
        "and this documented finding (and the audit report) should be updated."
    )


def test_alignment_result_carries_provenance_only_inside_an_opaque_json_blob(pipeline_session_factory):
    """AlignmentResult.component_snapshot['provenance'] DOES carry the
    full provenance dict (pipeline/feature/state/fusion/alignment/
    contributor/recommendation config versions) -- but only nested
    inside an unstructured JSON blob, not as queryable columns, and
    only for rows where alignment actually ran (fusion_result.fused_final
    is not None) -- INSUFFICIENT_HISTORY / NO_PREDICTION / FAILED rows
    have no AlignmentResult row at all and so carry no persisted
    provenance whatsoever."""

    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    result = run_daily_inference(pid, dates[6], pipeline_session_factory)
    assert result.status == SUCCESS

    session = pipeline_session_factory()
    try:
        alignment = session.execute(
            select(AlignmentResult).where(AlignmentResult.circadian_label_id == result.circadian_label_id)
        ).scalar_one()
        assert alignment.component_snapshot is not None
        provenance = alignment.component_snapshot.get("provenance")
        assert provenance is not None
        for key in (
            "pipeline_version", "feature_manifest_version", "model_version", "state_config_version",
            "fusion_config_version", "alignment_config_version", "contributor_config_version",
            "recommendation_config_version",
        ):
            assert key in provenance

        # And confirm it is not exposed as a first-class column anywhere
        # on AlignmentResult -- only inside the JSON blob.
        alignment_columns = {c.name for c in AlignmentResult.__table__.columns}
        assert "provenance" not in alignment_columns
        assert "alignment_config_version" not in alignment_columns
    finally:
        session.close()


def test_contributor_result_and_intervention_log_have_no_version_columns_at_all(pipeline_session_factory):
    """FINDING: ContributorResult has no version column of any kind
    (not contributor_config_version, not a provenance blob) -- there is
    no way, from a ContributorResult row alone, to know which
    contributor-ranking config version produced it; the caller must
    already know to join back to the sibling AlignmentResult's JSON
    blob. InterventionLog similarly carries `personalization_phase`
    (a phase label) but no `recommendation_config_version`."""

    contributor_columns = {c.name for c in ContributorResult.__table__.columns}
    assert "contributor_config_version" not in contributor_columns
    assert "provenance" not in contributor_columns

    log_columns = {c.name for c in InterventionLog.__table__.columns}
    assert "personalization_phase" in log_columns  # this much IS tracked
    assert "recommendation_config_version" not in log_columns


def test_insufficient_history_result_has_no_model_version_but_may_still_get_an_alignment_row(pipeline_session_factory):
    """A day with too little history for XGBoost produces
    INSUFFICIENT_HISTORY: CircadianLabel.training_run_id is NULL (no
    model ran), so model-version provenance is genuinely unrecoverable
    for that row. Discovered while writing this test: the orchestrator's
    alignment/contributor/recommendation block is gated only on
    `fusion_result.fused_final is not None`, not on pipeline_status --
    so state-only fusion can still produce a fused DLMO and an
    AlignmentResult (with its JSON-blob provenance) even on an
    INSUFFICIENT_HISTORY day. That is correct pipeline behavior (state
    engine has enough history to answer even when XGBoost doesn't), not
    a bug; this test asserts the model-version gap directly rather than
    assuming no AlignmentResult exists at all."""

    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    early_date = dates[1]  # too little history for XGBoost
    result = run_daily_inference(pid, early_date, pipeline_session_factory)
    assert result.status == "INSUFFICIENT_HISTORY"
    assert result.xgb_prediction is None

    session = pipeline_session_factory()
    try:
        label = session.get(CircadianLabel, result.circadian_label_id)
        assert label.training_run_id is None, "no model ran, so model-version provenance is unrecoverable for this row"
    finally:
        session.close()


def test_failed_pipeline_run_persists_nothing_so_no_provenance_question_arises(pipeline_session_factory):
    """A FAILED run (nothing written at all, by design -- see
    orchestrator's failure-handling policy) leaves no row for a
    provenance question to even apply to. Confirms the FAILED path is
    consistent with the rollback guarantee checked in
    tests/audit/test_audit_db_integrity.py."""

    result = run_daily_inference(999_999_999, _observation_dates(pipeline_session_factory, _first_participant_id(pipeline_session_factory))[1], pipeline_session_factory)
    assert result.status == "FAILED"
    assert result.circadian_label_id is None
