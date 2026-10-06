"""Read/write adapter between the Phase 2 schema and the safety layer.
Uses only ``circadian_labels``, ``alignment_results``, ``intervention_log``,
and ``safety_flags`` -- no parallel safety database.
"""

from __future__ import annotations

from datetime import date as date_cls, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import AlignmentResult, CircadianLabel, InterventionLog, SafetyFlag as SafetyFlagRow
from app.safety.config import DEFAULT_SAFETY_CONFIG, SafetyConfig
from app.safety.lifecycle import LifecycleDecision
from app.safety.messages import FLAG_MESSAGE_KEYS, FLAG_MESSAGES
from app.safety.patterns import DayRecord
from app.synthetic.time_utils import clock_time_to_hour


def load_rolling_records(
    session: Session, participant_id: int, as_of_date: date_cls, config: SafetyConfig = DEFAULT_SAFETY_CONFIG
) -> list:
    """The most recent ``rolling_horizon_days`` days strictly before
    ``as_of_date`` (today's own not-yet-complete day is never included
    as evidence)."""

    window_start = as_of_date - timedelta(days=config.rolling_horizon_days)

    labels = {
        row.target_date: row
        for row in session.execute(
            select(CircadianLabel).where(
                CircadianLabel.participant_id == participant_id,
                CircadianLabel.target_date >= window_start,
                CircadianLabel.target_date < as_of_date,
                CircadianLabel.is_latest.is_(True),
            )
        ).scalars().all()
    }
    compliance = {
        row.log_date: row.compliance_degree
        for row in session.execute(
            select(InterventionLog).where(
                InterventionLog.participant_id == participant_id,
                InterventionLog.log_date >= window_start,
                InterventionLog.log_date < as_of_date,
            )
        ).scalars().all()
    }

    records = []
    cursor = window_start
    while cursor < as_of_date:
        label = labels.get(cursor)
        prediction_available = label is not None and label.fused_dlmo_time is not None
        dlmo_hour = clock_time_to_hour(label.fused_dlmo_time) if prediction_available else None
        alignment_score = (
            label.alignment_result.final_alignment_score if label is not None and label.alignment_result is not None else None
        )
        records.append(
            DayRecord(
                date=cursor, prediction_available=prediction_available, dlmo_hour=dlmo_hour,
                alignment_score=alignment_score, compliance_degree=compliance.get(cursor),
            )
        )
        cursor += timedelta(days=1)

    return records


def load_open_flags(session: Session, participant_id: int) -> dict:
    """``flag_type -> SafetyFlag`` (ORM row) for every currently-open
    (``resolved_date IS NULL``) flag -- one open row per type at most."""

    rows = session.execute(
        select(SafetyFlagRow).where(SafetyFlagRow.participant_id == participant_id, SafetyFlagRow.resolved_date.is_(None))
    ).scalars().all()
    by_type: dict = {}
    for row in rows:
        by_type[row.flag_type] = row
    return by_type


def apply_lifecycle_decision(
    session: Session,
    participant_id: int,
    as_of_date: date_cls,
    decision: LifecycleDecision,
    existing_row: Optional[SafetyFlagRow],
    config: SafetyConfig = DEFAULT_SAFETY_CONFIG,
) -> Optional[SafetyFlagRow]:
    """Creates a new row for a freshly DETECTED flag, or mutates only
    the fields ``safety_flags`` documents as mutable
    (``last_observed_date``, and ``resolved_date``/``resolved_by`` on
    resolution) on an existing open row -- everything else on an
    existing row (severity, message, triggering_statistics at
    creation) is left untouched, per that table's append-only
    contract."""

    from app.safety.enums import DETECTED, PERSISTING, RESOLVED

    if decision.lifecycle_state == DETECTED:
        row = SafetyFlagRow(
            participant_id=participant_id, flagged_date=as_of_date, flag_type=decision.flag_type,
            severity=decision.severity, message_shown=FLAG_MESSAGES[decision.flag_type],
            message_key=FLAG_MESSAGE_KEYS[decision.flag_type],
            recommendation_suppressed=(decision.severity == "HIGH"),
            first_detected_date=as_of_date, last_observed_date=as_of_date,
            triggering_statistics=decision.triggering_statistics, detection_version=config.safety_config_version,
        )
        session.add(row)
        session.flush()
        return row

    if decision.lifecycle_state == PERSISTING and existing_row is not None:
        existing_row.last_observed_date = as_of_date
        return existing_row

    if decision.lifecycle_state == RESOLVED and existing_row is not None:
        existing_row.resolved_date = as_of_date
        existing_row.resolved_by = f"detection_version:{config.safety_config_version}"
        return existing_row

    return existing_row


def update_circadian_label_safety_metadata(
    session: Session, participant_id: int, target_date: date_cls, status: str, recommendation_suppressed: bool, severity: Optional[str]
) -> None:
    label = session.execute(
        select(CircadianLabel).where(
            CircadianLabel.participant_id == participant_id, CircadianLabel.target_date == target_date, CircadianLabel.is_latest.is_(True)
        )
    ).scalars().first()
    if label is None:
        return
    label.safe_output_status = status
    label.recommendation_suppressed = recommendation_suppressed
    label.safety_severity = severity
