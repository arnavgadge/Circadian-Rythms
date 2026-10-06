"""Read-side adapter between the Phase 2 database and the recommendation
engine. Read-only, mirroring ``app.state.db_adapter`` /
``app.alignment.db_adapter`` / ``app.contributors.db_adapter``: this
module only translates existing ORM rows into the engine's own types.
Writing a selected recommendation into ``intervention_log`` is left to
whatever later phase owns that write path.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import DailyObservation, InterventionLog, Recommendation
from app.recommendations.catalogue import CandidateIntervention, intervention_from_recommendation
from app.recommendations.behavior import BehavioralHistory
from app.recommendations.config import DEFAULT_RECOMMENDATION_CONFIG, RecommendationConfig
from app.recommendations.cooldown import PriorPrimary
from app.recommendations.feasibility import RecentComplianceRecord
from app.synthetic.time_utils import clock_time_to_hour


def load_candidate_interventions(session: Session, active_only: bool = True) -> list:
    """Load the full catalogue from ``recommendations`` -- the only
    source of candidate interventions; nothing here is hard-coded."""

    stmt = select(Recommendation)
    if active_only:
        stmt = stmt.where(Recommendation.is_active.is_(True))
    rows = session.execute(stmt).scalars().all()
    return [intervention_from_recommendation(row) for row in rows]


def _hour_or_none(value) -> Optional[float]:
    return clock_time_to_hour(value) if value is not None else None


def build_behavioral_history(
    window_observations: Sequence[DailyObservation], actual_sleep_onset_hour: Optional[float] = None
) -> BehavioralHistory:
    """Build :class:`BehavioralHistory` from raw ``daily_observations``
    rows -- the same six-day window Phase 9's db_adapter consumes."""

    if actual_sleep_onset_hour is None and window_observations:
        last = window_observations[-1]
        actual_sleep_onset_hour = _hour_or_none(last.sleep_onset_time)

    return BehavioralHistory(
        actual_sleep_onset_hour=actual_sleep_onset_hour,
        window_evening_screen_duration_hours=[
            (o.evening_screen_duration_minutes / 60.0) if o.evening_screen_duration_minutes is not None else None
            for o in window_observations
        ],
        window_morning_light_duration_minutes=[o.morning_light_duration_minutes for o in window_observations],
        window_last_meal_hours=[_hour_or_none(o.last_meal_time) for o in window_observations],
        window_exercise_hours=[_hour_or_none(o.exercise_time) for o in window_observations],
        window_social_jetlag_minutes=[o.social_jetlag_minutes for o in window_observations],
    )


def load_recent_compliance(
    session: Session,
    participant_id: int,
    as_of: date,
    config: RecommendationConfig = DEFAULT_RECOMMENDATION_CONFIG,
) -> dict:
    """``intervention_id -> tuple[RecentComplianceRecord, ...]`` for the
    configured lookback window, for use as feasibility history."""

    lookback_start = as_of - timedelta(days=config.recent_history_lookback_days)
    rows = session.execute(
        select(InterventionLog).where(
            InterventionLog.participant_id == participant_id,
            InterventionLog.log_date >= lookback_start,
            InterventionLog.log_date < as_of,
        )
    ).scalars().all()

    by_intervention: dict = {}
    for row in rows:
        by_intervention.setdefault(row.recommendation_id, []).append(
            RecentComplianceRecord(compliance_binary=row.compliance_binary, compliance_degree=row.compliance_degree)
        )
    return {k: tuple(v) for k, v in by_intervention.items()}


def load_prior_primary(session: Session, participant_id: int, as_of: date) -> Optional[PriorPrimary]:
    """The most recent prior day's primary intervention (``InterventionLog``
    does not itself carry a priority field, so callers that write the log
    are expected to record priority 1 recommendations distinguishably --
    see ``docs/recommendation_engine.md`` "Intervention history"; this
    reads whatever the most recent logged row for the participant was)."""

    row = session.execute(
        select(InterventionLog)
        .where(InterventionLog.participant_id == participant_id, InterventionLog.log_date < as_of)
        .order_by(InterventionLog.log_date.desc())
    ).scalars().first()

    if row is None:
        return None
    return PriorPrimary(intervention_id=row.recommendation_id, log_date=row.log_date)
