"""Read-side adapter: reconstructs everything Phase 12 needs (baseline
period, intervention period, compliance, outcomes) purely from SQL --
``intervention_log``, ``circadian_labels``, ``alignment_results``,
``daily_observations``, ``participants``. No parallel in-memory source
of truth is maintained; every effect estimate can be recomputed from
these same tables at any time (see docs "Recomputation").
"""

from __future__ import annotations

from datetime import date as date_cls, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import CircadianLabel, DailyObservation, InterventionLog, Recommendation
from app.effectiveness.actuals import resolve_actual_value
from app.effectiveness.config import DEFAULT_EFFECTIVENESS_CONFIG, EffectivenessConfig
from app.effectiveness.phase1 import DayRecord
from app.effectiveness.windows import InterventionEpisode, detect_episodes
from app.recommendations.catalogue import intervention_from_recommendation
from app.recommendations.catalogue import CandidateIntervention
from app.synthetic.time_utils import clock_time_to_hour

_SIGNALS = ("evening_screen", "morning_light", "meal_timing", "exercise", "social_jetlag")


def load_target_signal(session: Session, recommendation_id: int) -> str:
    from app.effectiveness.compliance import resolve_dispatch_key

    recommendation = session.get(Recommendation, recommendation_id)
    candidate: CandidateIntervention = intervention_from_recommendation(recommendation)
    return resolve_dispatch_key(candidate.contributor_signals, candidate.intervention_type)


def load_episodes(
    session: Session, participant_id: int, recommendation_id: int, as_of_date: Optional[date_cls] = None
) -> list:
    """``as_of_date``, when given, restricts to log rows dated strictly
    before it -- callers that need a temporally-scoped view (e.g. the
    Phase 13 personalization update pipeline reconstructing "what was
    known as of day t") must pass it; omitting it preserves the
    original "full history through today" behavior for callers that
    intentionally want that (diagnostics scripts, tests running against
    a database with no future rows)."""

    query = select(InterventionLog).where(
        InterventionLog.participant_id == participant_id, InterventionLog.recommendation_id == recommendation_id
    )
    if as_of_date is not None:
        query = query.where(InterventionLog.log_date < as_of_date)
    log_rows = session.execute(query.order_by(InterventionLog.log_date.asc())).scalars().all()
    return detect_episodes(log_rows)


def load_intervention_records(
    session: Session,
    participant_id: int,
    recommendation_id: int,
    config: EffectivenessConfig = DEFAULT_EFFECTIVENESS_CONFIG,
    as_of_date: Optional[date_cls] = None,
) -> dict:
    """``date -> DayRecord`` spanning the participant's full available
    history relevant to ``recommendation_id``: every compliance day
    this recommendation was ever logged, plus the
    ``baseline_window_days`` immediately before the earliest such day
    (so a baseline window is always reconstructable), through today --
    or, when ``as_of_date`` is given, through the day strictly before
    it, and no log row dated on/after it is read at all (see
    ``load_episodes``).
    """

    query = select(InterventionLog).where(
        InterventionLog.participant_id == participant_id, InterventionLog.recommendation_id == recommendation_id
    )
    if as_of_date is not None:
        query = query.where(InterventionLog.log_date < as_of_date)
    log_rows = session.execute(query.order_by(InterventionLog.log_date.asc())).scalars().all()
    if not log_rows:
        return {}

    compliance_by_date = {row.log_date: row.compliance_degree for row in log_rows}
    range_start = log_rows[0].log_date - timedelta(days=config.baseline_window_days)
    range_end = log_rows[-1].log_date
    if as_of_date is not None:
        range_end = min(range_end, as_of_date - timedelta(days=1))

    observations = {
        row.observation_date: row
        for row in session.execute(
            select(DailyObservation).where(
                DailyObservation.participant_id == participant_id,
                DailyObservation.observation_date >= range_start,
                DailyObservation.observation_date <= range_end,
            )
        ).scalars().all()
    }

    labels = {
        row.target_date: row
        for row in session.execute(
            select(CircadianLabel).where(
                CircadianLabel.participant_id == participant_id,
                CircadianLabel.target_date >= range_start,
                CircadianLabel.target_date <= range_end,
                CircadianLabel.is_latest.is_(True),
            )
        ).scalars().all()
    }

    records: dict = {}
    cursor = range_start
    while cursor <= range_end:
        observation = observations.get(cursor)
        label = labels.get(cursor)

        dlmo_hour = clock_time_to_hour(label.fused_dlmo_time) if label is not None and label.fused_dlmo_time is not None else None
        alignment_score = label.alignment_result.final_alignment_score if label is not None and label.alignment_result is not None else None

        actual_sleep_onset_hour = (
            clock_time_to_hour(observation.sleep_onset_time)
            if observation is not None and observation.sleep_onset_time is not None
            else None
        )
        signal_values = {signal: resolve_actual_value(signal, observation, actual_sleep_onset_hour) for signal in _SIGNALS}

        records[cursor] = DayRecord(
            date=cursor,
            dlmo_hour=dlmo_hour,
            alignment_score=alignment_score,
            signal_values=signal_values,
            compliance_degree=compliance_by_date.get(cursor),
        )
        cursor += timedelta(days=1)

    return records


def load_current_episode(episodes: list) -> Optional[InterventionEpisode]:
    """The most recent episode -- used as "the" episode for Phase 1/2
    (before/after and matching are evaluated relative to the latest
    time this intervention was recommended)."""

    return episodes[-1] if episodes else None
