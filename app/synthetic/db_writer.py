"""Writes a generated :class:`SyntheticDataset` into the Phase 2 schema.

SQL is the authoritative store for this data -- this module is the
only place synthetic rows are turned into ``Participant``,
``ParticipantProfile``, ``DailyObservation``, ``PhysiologyLog``, and
``CircadianLabel`` ORM rows and committed.

**Where the synthetic "ground truth" DLMO lives**: ``circadian_labels``
was designed (Phase 2) to hold circadian-phase estimates, immutable
per prediction event. This phase writes one ``CircadianLabel`` row per
participant per day with ``prediction_status="synthetic_ground_truth"``
and only ``fused_dlmo_*`` populated (``xgboost_dlmo_*`` and
``state_model_dlmo_time`` are left ``NULL``, since no model has made a
prediction yet). Later phases will write additional rows for the same
dates with ``prediction_status="success"`` once a real model exists;
the two kinds of rows are distinguished by ``prediction_status``, never
conflated. See ``docs/synthetic_data_generation.md`` section 9.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import delete, insert
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import (
    CircadianLabel,
    DailyObservation,
    Participant,
    ParticipantProfile,
    PhysiologyLog,
)
from app.synthetic.simulator import SyntheticDataset
from app.synthetic.time_utils import hour_to_clock_time

_CHRONOTYPE_DISPLAY = {"early": "Early", "intermediate": "Intermediate", "late": "Late"}

_BATCH_SIZE = 5000


@dataclass
class WriteResult:
    participants_written: int
    daily_observations_written: int
    physiology_logs_written: int
    circadian_labels_written: int


def reset_all_participants(session_factory: sessionmaker[Session]) -> int:
    """Delete every participant (and, via ``ON DELETE CASCADE``, every
    row that depends on one). Never called unless the caller explicitly
    asked for a reset -- see ``app/scripts/generate_synthetic_data.py``.
    """

    session = session_factory()
    try:
        result = session.execute(delete(Participant))
        session.commit()
        return result.rowcount or 0
    finally:
        session.close()


def _hour_or_none(value):
    if value is None or pd.isna(value):
        return None
    return hour_to_clock_time(float(value))


def _float_or_none(value):
    if value is None or pd.isna(value):
        return None
    return float(value)


def write_dataset_to_db(
    dataset: SyntheticDataset, session_factory: sessionmaker[Session]
) -> WriteResult:
    session = session_factory()
    try:
        participant_id_by_index = _write_participants_and_profiles(session, dataset)
        session.commit()

        daily_count = _write_daily_and_physiology(session, dataset, participant_id_by_index)
        session.commit()

        label_count = _write_circadian_labels(session, dataset, participant_id_by_index)
        session.commit()

        return WriteResult(
            participants_written=len(participant_id_by_index),
            daily_observations_written=daily_count,
            physiology_logs_written=daily_count,
            circadian_labels_written=label_count,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _write_participants_and_profiles(session: Session, dataset: SyntheticDataset) -> dict:
    manifest = {
        "seed": dataset.run_config.seed,
        "generator_version": dataset.run_config.generator_version,
        "config_version": dataset.run_config.config_version,
        "generated_at": dataset.generated_at.isoformat(),
    }

    p_df = dataset.participants_df
    participant_orm_objects = []
    for row in p_df.itertuples(index=False):
        participant_orm_objects.append(
            Participant(
                participant_code=row.participant_code,
                enrollment_date=dataset.generated_at.date(),
                status="active",
            )
        )
    session.add_all(participant_orm_objects)
    session.flush()  # populate .id for each object

    participant_id_by_index = {
        int(row.index): obj.id for row, obj in zip(p_df.itertuples(index=False), participant_orm_objects)
    }

    profile_objects = []
    for row in p_df.itertuples(index=False):
        profile_objects.append(
            ParticipantProfile(
                participant_id=participant_id_by_index[int(row.index)],
                chronotype_category=_CHRONOTYPE_DISPLAY[row.chronotype],
                intrinsic_dlmo_time=_hour_or_none(row.intrinsic_dlmo_hour),
                adapted_dlmo_time=_hour_or_none(row.final_adapted_dlmo_hour),
                current_dlmo_time=_hour_or_none(row.final_current_dlmo_hour),
                current_dlmo_date=dataset.generated_at.date(),
                meq_score=float(row.meq_score),
                meq_category=row.meq_category,
                msfsc_time=_hour_or_none(row.msfsc_baseline_hour),
                synthetic_personality_profile={
                    "personality": row.personality_key,
                    "light_sensitivity": row.light_sensitivity,
                    "screen_sensitivity": row.screen_sensitivity,
                    "meal_sensitivity": row.meal_sensitivity,
                    "generation": manifest,
                },
            )
        )
    session.add_all(profile_objects)
    return participant_id_by_index


def _write_daily_and_physiology(
    session: Session, dataset: SyntheticDataset, participant_id_by_index: dict
) -> int:
    d_df = dataset.daily_df
    total = 0

    for start in range(0, len(d_df), _BATCH_SIZE):
        chunk = d_df.iloc[start : start + _BATCH_SIZE]

        daily_rows = []
        physiology_rows = []
        for row in chunk.itertuples(index=False):
            participant_id = participant_id_by_index[int(row.participant_index)]
            daily_rows.append(
                {
                    "participant_id": participant_id,
                    "observation_date": row.date,
                    "sleep_onset_time": _hour_or_none(row.sleep_onset_hour),
                    "sleep_offset_time": _hour_or_none(row.sleep_offset_hour),
                    "sleep_duration_minutes": row.sleep_duration_hours * 60.0,
                    "sleep_midpoint_time": _hour_or_none(row.sleep_midpoint_hour),
                    "sleep_midpoint_variability_minutes": _float_or_none(
                        row.sleep_midpoint_variability_minutes
                    ),
                    "is_free_day": bool(row.is_free_day),
                    "free_day_sleep_onset_time": _hour_or_none(row.free_day_sleep_onset_hour),
                    "free_day_sleep_offset_time": _hour_or_none(row.free_day_sleep_offset_hour),
                    "free_day_sleep_midpoint_time": _hour_or_none(row.free_day_sleep_midpoint_hour),
                    "social_jetlag_minutes": _float_or_none(row.social_jetlag_minutes),
                    "free_day_ratio": None,  # windowed feature; computed in Phase 4
                    "msfsc_time": None,  # participant-level baseline lives on participant_profiles
                    "morning_light_start_time": _hour_or_none(row.morning_light_start_hour),
                    "morning_light_duration_minutes": row.morning_light_duration_minutes,
                    "evening_screen_end_time": _hour_or_none(row.evening_screen_end_hour),
                    "evening_screen_duration_minutes": row.evening_screen_duration_hours * 60.0,
                    "last_meal_time": _hour_or_none(row.last_meal_hour),
                    "meal_to_sleep_gap_minutes": row.meal_to_sleep_gap_minutes,
                    "exercise_time": _hour_or_none(row.exercise_hour),
                    "exercise_duration_minutes": row.exercise_duration_minutes,
                    "last_caffeine_time": _hour_or_none(row.caffeine_hour),
                    "caffeine_amount_mg": row.caffeine_amount_mg,
                }
            )
            physiology_rows.append(
                {
                    "participant_id": participant_id,
                    "observation_date": row.date,
                    "resting_heart_rate_bpm": row.resting_hr_bpm,
                    "hrv_ms": row.hrv_ms,
                    "wrist_temperature_c": row.wrist_temp_c,
                }
            )

        session.execute(insert(DailyObservation), daily_rows)
        session.execute(insert(PhysiologyLog), physiology_rows)
        total += len(daily_rows)

    return total


def _write_circadian_labels(
    session: Session, dataset: SyntheticDataset, participant_id_by_index: dict
) -> int:
    d_df = dataset.daily_df
    total = 0

    for start in range(0, len(d_df), _BATCH_SIZE):
        chunk = d_df.iloc[start : start + _BATCH_SIZE]

        label_rows = []
        for row in chunk.itertuples(index=False):
            label_rows.append(
                {
                    "participant_id": participant_id_by_index[int(row.participant_index)],
                    "target_date": row.date,
                    "is_latest": True,
                    "prediction_status": "synthetic_ground_truth",
                    "fused_dlmo_time": hour_to_clock_time(row.current_dlmo_hour),
                    "data_completeness": 1.0,
                }
            )
        session.execute(insert(CircadianLabel), label_rows)
        total += len(label_rows)

    return total
