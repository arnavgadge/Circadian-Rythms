"""The pipeline's READ phase.

Everything here is a plain, read-only query against the Phase 2
schema -- no computation, no writes. Kept separate from
``orchestrator.py`` so the "read everything -> compute everything ->
write everything" structure (see ``docs/daily_inference_pipeline.md``
"Transaction boundary") is visible at a glance: nothing in this module
ever opens a write transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_cls, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import CircadianLabel, DailyObservation, Participant, ParticipantProfile
from app.pipeline.config import DEFAULT_PIPELINE_CONFIG, PipelineConfig


@dataclass(frozen=True)
class ReadResult:
    participant: Participant
    profile: ParticipantProfile
    window_observations: tuple  # consecutive DailyObservation rows immediately before target_date, oldest first
    history_days_available: int  # length of the above (0 if yesterday itself is missing)
    previous_label: Optional[CircadianLabel]  # is_latest row for target_date - 1, if any


def _consecutive_prior_observations(
    session: Session, participant_id: int, target_date: date_cls, lookback_days: int
) -> list:
    """Every ``daily_observations`` row for ``participant_id`` in the
    ``lookback_days`` immediately before ``target_date``, oldest first,
    but only the **unbroken run ending at ``target_date - 1``** -- a
    gap anywhere in the run truncates it there, since a six-day window
    with a hole in it is not a valid six-day window (see
    ``app.features.windows.compute_valid_windows``'s identical
    consecutive-run requirement, applied here without duplicating that
    bulk-history logic).
    """

    window_start = target_date - timedelta(days=lookback_days)
    window_end = target_date - timedelta(days=1)

    rows = session.execute(
        select(DailyObservation)
        .where(
            DailyObservation.participant_id == participant_id,
            DailyObservation.observation_date >= window_start,
            DailyObservation.observation_date <= window_end,
        )
        .order_by(DailyObservation.observation_date.asc())
    ).scalars().all()

    by_date = {row.observation_date: row for row in rows}

    consecutive: list = []
    cursor = window_end
    while cursor in by_date:
        consecutive.append(by_date[cursor])
        cursor -= timedelta(days=1)
    consecutive.reverse()
    return consecutive


def read_daily_inference_inputs(
    session: Session,
    participant_id: int,
    target_date: date_cls,
    config: PipelineConfig = DEFAULT_PIPELINE_CONFIG,
) -> ReadResult:
    """STEP 1-3 of the daily pipeline: participant state, the six
    previous complete days, and the previous day's fused result.

    Validates: the participant exists, no observation in the returned
    window is on or after ``target_date`` (no target-day leakage), and
    every row belongs to ``participant_id`` (defensive -- the query
    itself already filters on it, but a mismatch here would indicate a
    real bug rather than expected input variation, so it raises).
    """

    participant = session.get(Participant, participant_id)
    if participant is None:
        raise ValueError(f"No participant with id={participant_id}")

    profile = session.get(ParticipantProfile, participant_id)
    if profile is None:
        raise ValueError(f"Participant {participant_id} has no participant_profiles row")

    window_observations = _consecutive_prior_observations(
        session, participant_id, target_date, config.min_consecutive_history_days
    )

    for obs in window_observations:
        if obs.observation_date >= target_date:
            raise ValueError(
                f"Target-day leakage: observation dated {obs.observation_date} is not before {target_date}"
            )
        if obs.participant_id != participant_id:
            raise ValueError("Window observation participant_id mismatch")

    previous_label = session.execute(
        select(CircadianLabel).where(
            CircadianLabel.participant_id == participant_id,
            CircadianLabel.target_date == target_date - timedelta(days=1),
            CircadianLabel.is_latest.is_(True),
        )
    ).scalars().first()

    return ReadResult(
        participant=participant,
        profile=profile,
        window_observations=tuple(window_observations),
        history_days_available=len(window_observations),
        previous_label=previous_label,
    )


def get_latest_label_for_date(session: Session, participant_id: int, target_date: date_cls) -> Optional[CircadianLabel]:
    """Used for the idempotency short-circuit: does a completed result
    for this exact participant/date already exist?"""

    return session.execute(
        select(CircadianLabel).where(
            CircadianLabel.participant_id == participant_id,
            CircadianLabel.target_date == target_date,
            CircadianLabel.is_latest.is_(True),
        )
    ).scalars().first()
