"""Tests for the alignment engine's read-side database adapter, against
a real small Phase 3 synthetic dataset.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.alignment.db_adapter import build_alignment_inputs
from app.alignment.engine import compute_alignment
from app.database.models import CircadianLabel, DailyObservation, Participant, ParticipantProfile
from app.features.windows import compute_valid_windows
from app.synthetic.time_utils import clock_time_to_hour


def _first_participant_id(session) -> int:
    return session.execute(select(Participant.id).order_by(Participant.id)).scalars().first()


def test_build_alignment_inputs_from_real_observations(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    observations = small_synthetic_session.execute(
        select(DailyObservation).where(DailyObservation.participant_id == pid).order_by(DailyObservation.observation_date)
    ).scalars().all()
    window = observations[:6]

    inputs = build_alignment_inputs(fused_dlmo_hour=21.5, window_observations=window)

    assert len(inputs.window_sleep_onset_hours) == 6
    assert inputs.most_recent_sleep_onset_hour == clock_time_to_hour(window[-1].sleep_onset_time)
    assert all(0.0 <= h < 24.0 for h in inputs.window_sleep_onset_hours if h is not None)


def test_end_to_end_alignment_from_database(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    profile = small_synthetic_session.get(ParticipantProfile, pid)

    dates = list(
        small_synthetic_session.execute(
            select(DailyObservation.observation_date).where(DailyObservation.participant_id == pid)
        ).scalars().all()
    )
    windows = compute_valid_windows(pid, dates, window_size_days=6)
    window = windows[0]

    label = small_synthetic_session.execute(
        select(CircadianLabel).where(
            CircadianLabel.participant_id == pid,
            CircadianLabel.target_date == window.target_date,
            CircadianLabel.is_latest.is_(True),
        )
    ).scalars().first()
    assert label is not None and label.fused_dlmo_time is not None

    observations = {
        o.observation_date: o
        for o in small_synthetic_session.execute(
            select(DailyObservation).where(DailyObservation.participant_id == pid)
        ).scalars().all()
    }
    window_obs = [observations[d] for d in window.day_dates]

    inputs = build_alignment_inputs(
        fused_dlmo_hour=clock_time_to_hour(label.fused_dlmo_time),
        window_observations=window_obs,
        chronotype=profile.chronotype_category,
    )
    result = compute_alignment(inputs)

    assert 0.0 <= result.final_score <= 100.0
    assert result.data_completeness == 1.0  # Phase 3 synthetic data has no missing values
    assert result.imputed_components == []
