"""The pipeline's WRITE phase: one atomic transaction per daily result.

Everything in this module operates on an already-open ``Session`` and
performs no computation of its own -- by the time anything here runs,
every upstream Phase 4-10 result has already been fully computed (see
``docs/daily_inference_pipeline.md`` "Transaction boundary": expensive
ML/model work must never happen while a write transaction is open).
The caller is responsible for wrapping the call in
``app.database.engine.session_scope`` (or an equivalent try/commit/
rollback block) so a failure partway through leaves nothing committed.
"""

from __future__ import annotations

import dataclasses
from datetime import date as date_cls, datetime, timezone
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.database.models import (
    AlignmentResult as AlignmentResultRow,
    CircadianLabel,
    ContributorResult as ContributorResultRow,
    InterventionLog,
    ParticipantProfile,
    TrainingRun,
)
from app.synthetic.time_utils import hour_to_clock_time


def supersede_existing_label(session: Session, participant_id: int, target_date: date_cls) -> None:
    """Flip any existing ``is_latest`` row for this participant/date to
    ``False`` before inserting a new one -- the explicit "versioned
    rerun" path (see docs "Historical immutability"). Under normal
    operation there is nothing to flip, since the orchestrator's
    idempotency short-circuit prevents reaching this point at all
    unless a rerun was explicitly requested."""

    session.execute(
        update(CircadianLabel)
        .where(
            CircadianLabel.participant_id == participant_id,
            CircadianLabel.target_date == target_date,
            CircadianLabel.is_latest.is_(True),
        )
        .values(is_latest=False)
    )


def get_or_create_training_run(session: Session, model_type: str, model_version: str, metadata: dict) -> TrainingRun:
    existing = session.execute(
        select(TrainingRun).where(TrainingRun.model_type == model_type, TrainingRun.model_version == model_version)
    ).scalars().first()
    if existing is not None:
        return existing

    training_run = TrainingRun(
        model_type=model_type,
        model_version=model_version,
        num_participants=metadata.get("training_participant_count"),
        num_windows=metadata.get("training_window_count"),
        feature_count=metadata.get("feature_count"),
        cv_metrics=metadata.get("cv_metrics"),
        trained_at=_parse_training_date(metadata.get("training_date")),
        artifact_version=model_version,
    )
    session.add(training_run)
    session.flush()
    return training_run


def _parse_training_date(value) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return datetime.now(timezone.utc)


def _hour_or_none_to_time(hour: Optional[float]):
    return hour_to_clock_time(hour) if hour is not None else None


def write_circadian_label(
    session: Session,
    participant_id: int,
    target_date: date_cls,
    prediction_status: str,
    xgb_result: Optional[object],
    state_prediction: Optional[dict],
    fusion_result,
    feature_vector: Optional[object],
    training_run_id: Optional[int],
) -> CircadianLabel:
    """Insert the immutable ``CircadianLabel`` row for this event. Caller
    must have already called :func:`supersede_existing_label`."""

    label = CircadianLabel(
        participant_id=participant_id,
        target_date=target_date,
        is_latest=True,
        prediction_status=prediction_status,
        xgboost_dlmo_sin=xgb_result.predicted_sin if xgb_result is not None else None,
        xgboost_dlmo_cos=xgb_result.predicted_cos if xgb_result is not None else None,
        xgboost_dlmo_time=_hour_or_none_to_time(xgb_result.xgb_dlmo_hour) if xgb_result is not None else None,
        state_model_dlmo_time=_hour_or_none_to_time(
            state_prediction.get("state_dlmo_hour") if state_prediction else None
        ),
        fused_dlmo_time=_hour_or_none_to_time(fusion_result.fused_final if fusion_result else None),
        disagreement_minutes=fusion_result.disagreement_minutes if fusion_result else None,
        disagreement_regime=(
            fusion_result.disagreement_regime.value
            if fusion_result and fusion_result.disagreement_regime is not None
            else None
        ),
        confidence_score=fusion_result.final_confidence if fusion_result else None,
        confidence_label=(
            fusion_result.confidence_label.value if fusion_result and fusion_result.confidence_label else None
        ),
        data_completeness=feature_vector.completeness if feature_vector is not None else None,
        missing_features=list(feature_vector.missing_features) if feature_vector is not None else None,
        imputed_features=list(feature_vector.imputed_features) if feature_vector is not None else None,
        training_run_id=training_run_id,
    )
    session.add(label)
    session.flush()
    return label


def write_alignment_and_contributors(
    session: Session,
    circadian_label: CircadianLabel,
    participant_id: int,
    target_date: date_cls,
    alignment_result,
    contributor_result,
    provenance: dict,
) -> None:
    component_snapshot = {
        "behavioral_components": {
            name: dataclasses.asdict(component) for name, component in alignment_result.behavioral_components.items()
        },
        "provenance": provenance,
    }

    def _component_score(name: str) -> Optional[float]:
        component = alignment_result.behavioral_components.get(name)
        return component.score if component is not None else None

    alignment_row = AlignmentResultRow(
        circadian_label_id=circadian_label.id,
        participant_id=participant_id,
        target_date=target_date,
        final_alignment_score=alignment_result.final_score,
        phase_alignment_score=alignment_result.phase_score,
        behavioral_alignment_score=alignment_result.behavioral_score,
        sleep_consistency_score=_component_score("sleep_consistency"),
        morning_light_score=_component_score("morning_light"),
        evening_screen_score=_component_score("evening_screen"),
        meal_timing_score=_component_score("meal_timing"),
        social_jetlag_score=_component_score("social_jetlag"),
        ideal_sleep_onset_time=_hour_or_none_to_time(alignment_result.ideal_sleep_onset_hour),
        actual_sleep_onset_time=_hour_or_none_to_time(alignment_result.actual_sleep_onset_hour),
        component_snapshot=component_snapshot,
    )
    session.add(alignment_row)
    session.flush()

    if contributor_result is not None:
        for contributor in contributor_result.contributors:
            anomaly = contributor_result.anomaly_details.get(contributor.signal)
            if anomaly is None or not anomaly.available:
                anomaly_status = "unavailable"
            else:
                anomaly_status = "anomaly" if anomaly.is_anomaly else "no_anomaly"

            session.add(
                ContributorResultRow(
                    alignment_result_id=alignment_row.id,
                    participant_id=participant_id,
                    target_date=target_date,
                    rank=contributor.rank,
                    contributor_signal=contributor.signal,
                    effect_estimate=contributor.signed_phase_effect_minutes,
                    alignment_deficit=contributor.alignment_deficit,
                    direction=contributor.direction,
                    anomaly_status=anomaly_status,
                    contributor_score=contributor.contributor_score,
                    today_anomaly=contributor.today_anomaly,
                )
            )


def write_recommendation(
    session: Session,
    participant_id: int,
    target_date: date_cls,
    recommendation_result,
) -> None:
    """Exactly one ``intervention_log`` row per participant/date: any
    existing row for this date is superseded (deleted) first, so a
    rerun never leaves more than one "the recommendation given on this
    date" record -- see docs "Recommendation persistence". Only the
    primary recommendation is logged; supporting nudges are part of
    the returned structured result but the current schema has no
    per-day slot for more than one logged intervention (see docs
    "Limitations")."""

    session.execute(
        delete(InterventionLog).where(
            InterventionLog.participant_id == participant_id, InterventionLog.log_date == target_date
        )
    )

    if recommendation_result is None or recommendation_result.primary is None:
        return

    primary = recommendation_result.primary
    target_value_time = _hour_or_none_to_time(primary.target_value) if primary.target_unit == "clock_time" else None
    target_value_numeric = primary.target_value if primary.target_unit != "clock_time" else None

    session.add(
        InterventionLog(
            participant_id=participant_id,
            recommendation_id=primary.intervention_id,
            log_date=target_date,
            recommendation_text=primary.text,
            target_value_time=target_value_time,
            target_value_numeric=target_value_numeric,
            expected_improvement_minutes=primary.expected_improvement_minutes,
            personalization_phase=recommendation_result.personalization_phase,
        )
    )


def update_participant_state(
    session: Session,
    profile: ParticipantProfile,
    target_date: date_cls,
    new_current_dlmo_hour: Optional[float],
    new_adapted_dlmo_hour: Optional[float],
    new_alignment_score: Optional[float],
) -> None:
    """Mutates the CURRENT-state columns only -- chronotype and
    ``intrinsic_dlmo_time`` are never touched here (see docs "Current
    vs. historical state")."""

    if new_current_dlmo_hour is not None:
        profile.current_dlmo_time = hour_to_clock_time(new_current_dlmo_hour)
        profile.current_dlmo_date = target_date
    if new_adapted_dlmo_hour is not None:
        profile.adapted_dlmo_time = hour_to_clock_time(new_adapted_dlmo_hour)
    if new_alignment_score is not None:
        profile.current_alignment_score = new_alignment_score
        profile.current_alignment_date = target_date
