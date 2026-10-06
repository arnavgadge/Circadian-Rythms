"""AUDIT 21 -- Reproducibility (Phase 17 adversarial audit).

tests/test_pipeline.py::test_deterministic_replay_produces_same_fused_dlmo
already re-runs the pipeline twice off an identical restored snapshot
and compares fused_final / alignment final_score to 1e-9. This file
extends that same restore-snapshot-then-rerun harness to compare every
other component the audit spec calls out (XGBoost prediction, state
prediction, full alignment breakdown, contributor ranking, and the
selected recommendation) -- not just the two fields the existing test
checks -- and documents the personalization-engine finding below.

**Personalization finding (documented, not a bug to fix)**: the
Thompson-sampling contextual bandit in app.personalization.bandit
(`thompson_sample`) requires the caller to pass an explicit
`numpy.random.Generator` -- there is no implicit/unseeded global RNG
inside that module, so it is reproducible *given* a seeded generator.
However, app.pipeline.orchestrator.run_daily_inference never calls into
app.personalization at all (grep confirms no import); the recommendation
engine's own "personalization" concept (app.recommendations.personalization)
is a deterministic, non-random blend of literature/personal-effect
values gated by `personalization_phase`, reserved for a not-yet-wired
`ADAPTIVE_POLICY` phase. So "personalization state" reproducibility
cannot currently be exercised end-to-end through the daily pipeline --
there is no persisted bandit posterior for run_daily_inference to
produce or vary. This is reported as a scope/wiring gap, not a
reproducibility defect.
"""

from __future__ import annotations

import dataclasses

import pytest
from sqlalchemy import delete, select

from app.database.models import CircadianLabel, DailyObservation, InterventionLog, Participant, ParticipantProfile
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


def _snapshot_profile(session_factory, pid: int):
    session = session_factory()
    try:
        profile = session.get(ParticipantProfile, pid)
        return (
            profile.current_dlmo_time, profile.current_dlmo_date, profile.adapted_dlmo_time,
            profile.current_alignment_score, profile.current_alignment_date,
        )
    finally:
        session.close()


def _restore_profile_and_clear_label(session_factory, pid: int, target_date, snapshot):
    session = session_factory()
    try:
        session.execute(
            delete(CircadianLabel).where(
                CircadianLabel.participant_id == pid, CircadianLabel.target_date == target_date,
                CircadianLabel.prediction_status.in_(("success", "insufficient_history", "no_prediction")),
            )
        )
        session.execute(
            delete(InterventionLog).where(
                InterventionLog.participant_id == pid, InterventionLog.log_date == target_date
            )
        )
        profile = session.get(ParticipantProfile, pid)
        (
            profile.current_dlmo_time, profile.current_dlmo_date, profile.adapted_dlmo_time,
            profile.current_alignment_score, profile.current_alignment_date,
        ) = snapshot
        session.commit()
    finally:
        session.close()


def test_two_full_pipeline_runs_off_an_identical_snapshot_match_on_every_component(pipeline_session_factory):
    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    target_date = dates[6]

    snapshot = _snapshot_profile(pipeline_session_factory, pid)
    result_a = run_daily_inference(pid, target_date, pipeline_session_factory, force_rerun=True)
    assert result_a.status == SUCCESS

    _restore_profile_and_clear_label(pipeline_session_factory, pid, target_date, snapshot)
    result_b = run_daily_inference(pid, target_date, pipeline_session_factory, force_rerun=True)
    assert result_b.status == SUCCESS

    # --- XGBoost prediction ---
    assert result_a.xgb_prediction["xgb_dlmo_hour"] == pytest.approx(result_b.xgb_prediction["xgb_dlmo_hour"], abs=1e-9)
    assert result_a.xgb_prediction["model_version"] == result_b.xgb_prediction["model_version"]

    # --- State-engine prediction ---
    assert result_a.state_prediction["state_dlmo_hour"] == pytest.approx(result_b.state_prediction["state_dlmo_hour"], abs=1e-9)

    # --- Fusion ---
    assert result_a.fusion_result.fused_final == pytest.approx(result_b.fusion_result.fused_final, abs=1e-9)
    assert result_a.fusion_result.final_confidence == pytest.approx(result_b.fusion_result.final_confidence, abs=1e-9)
    assert result_a.fusion_result.disagreement_minutes == pytest.approx(result_b.fusion_result.disagreement_minutes, abs=1e-9)

    # --- Alignment (full breakdown, not just the final score) ---
    align_a, align_b = result_a.alignment_result, result_b.alignment_result
    assert align_a.final_score == pytest.approx(align_b.final_score, abs=1e-9)
    assert align_a.phase_score == pytest.approx(align_b.phase_score, abs=1e-9)
    assert align_a.behavioral_score == pytest.approx(align_b.behavioral_score, abs=1e-9)
    for name in align_a.behavioral_components:
        comp_a = align_a.behavioral_components[name]
        comp_b = align_b.behavioral_components[name]
        assert comp_a.score == pytest.approx(comp_b.score, abs=1e-9), f"component {name} diverged"

    # --- Contributors (ranking + scores) ---
    contrib_a, contrib_b = result_a.contributor_result.contributors, result_b.contributor_result.contributors
    assert [c.signal for c in contrib_a] == [c.signal for c in contrib_b]
    assert [c.rank for c in contrib_a] == [c.rank for c in contrib_b]
    for ca, cb in zip(contrib_a, contrib_b):
        assert ca.contributor_score == pytest.approx(cb.contributor_score, abs=1e-9)
        assert ca.signed_phase_effect_minutes == pytest.approx(cb.signed_phase_effect_minutes, abs=1e-9)

    # --- Recommendation ---
    rec_a, rec_b = result_a.recommendation_result, result_b.recommendation_result
    if rec_a.primary is None or rec_b.primary is None:
        assert rec_a.primary is None and rec_b.primary is None
    else:
        assert rec_a.primary.intervention_id == rec_b.primary.intervention_id
        assert rec_a.primary.text == rec_b.primary.text
        assert rec_a.primary.target_value == pytest.approx(rec_b.primary.target_value, abs=1e-9)
        assert rec_a.primary.expected_improvement_minutes == pytest.approx(
            rec_b.primary.expected_improvement_minutes, abs=1e-9
        )

    # --- Participant current-state update ---
    update_a, update_b = result_a.participant_state_update, result_b.participant_state_update
    assert update_a.new_current_dlmo_hour == pytest.approx(update_b.new_current_dlmo_hour, abs=1e-9)
    assert update_a.new_adapted_dlmo_hour == pytest.approx(update_b.new_adapted_dlmo_hour, abs=1e-9)
    assert update_a.new_alignment_score == pytest.approx(update_b.new_alignment_score, abs=1e-9)


def test_committed_rows_from_two_reproducible_runs_are_identical_in_the_database(pipeline_session_factory):
    """The same comparison, but read back from the database rather than
    the in-memory result object -- guards against a persistence bug
    that silently diverges from what was computed."""

    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    target_date = dates[6]

    snapshot = _snapshot_profile(pipeline_session_factory, pid)
    result_a = run_daily_inference(pid, target_date, pipeline_session_factory, force_rerun=True)
    session = pipeline_session_factory()
    label_a = session.get(CircadianLabel, result_a.circadian_label_id)
    fused_a, conf_a, disagree_a = label_a.fused_dlmo_time, label_a.confidence_score, label_a.disagreement_minutes
    session.close()

    _restore_profile_and_clear_label(pipeline_session_factory, pid, target_date, snapshot)
    result_b = run_daily_inference(pid, target_date, pipeline_session_factory, force_rerun=True)
    session = pipeline_session_factory()
    label_b = session.get(CircadianLabel, result_b.circadian_label_id)
    fused_b, conf_b, disagree_b = label_b.fused_dlmo_time, label_b.confidence_score, label_b.disagreement_minutes
    session.close()

    assert fused_a == fused_b
    assert conf_a == pytest.approx(conf_b, abs=1e-9)
    assert disagree_a == pytest.approx(disagree_b, abs=1e-9)


def test_personalization_bandit_sampling_requires_an_explicit_caller_supplied_rng():
    """Documents the actual reproducibility contract of the one place in
    this codebase that does sample randomly: app.personalization.bandit
    .thompson_sample takes rng as a required parameter with no default
    and touches no module-level/global random state, so it is
    reproducible whenever the caller seeds and reuses its own
    np.random.Generator -- but note (see module docstring above) this
    function is never invoked from the daily pipeline being audited."""

    import inspect

    from app.personalization.bandit import thompson_sample

    sig = inspect.signature(thompson_sample)
    assert "rng" in sig.parameters
    assert sig.parameters["rng"].default is inspect.Parameter.empty, (
        "thompson_sample must not default its rng parameter -- an implicit "
        "default would silently reintroduce unseeded randomness"
    )
