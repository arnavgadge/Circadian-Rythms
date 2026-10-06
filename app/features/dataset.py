"""The feature-dataset builder.

Turns a list of participants into the full feature matrix: for every
participant, every valid six-day window in their history becomes one
row. No training, no scaling, no global fitting -- tree-based XGBoost
(Phase 5) needs none of that, and fitting anything here would leak
information across rows/participants in a way this phase must not.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import DailyObservation, Participant
from app.features.builder import build_features
from app.features.config import DEFAULT_FEATURE_CONFIG, FeatureConfig
from app.features.feature_manifest import FEATURE_NAMES
from app.features.time_encoding import clock_to_sincos
from app.features.windows import compute_valid_windows


@dataclass
class FeatureDataset:
    X: pd.DataFrame
    feature_names: tuple
    metadata: pd.DataFrame
    targets: pd.DataFrame


def _participant_dates(session: Session, participant_id: int) -> list:
    return list(
        session.execute(
            select(DailyObservation.observation_date).where(
                DailyObservation.participant_id == participant_id
            )
        ).scalars().all()
    )


def build_feature_dataset(
    participant_ids: Sequence[int],
    session: Session,
    config: FeatureConfig = DEFAULT_FEATURE_CONFIG,
) -> FeatureDataset:
    """Build the full feature dataset for ``participant_ids``.

    Uses exactly the valid windows present in the database for each
    participant (see :func:`app.features.windows.compute_valid_windows`)
    -- 24 per participant for the Phase 3 30-day synthetic dataset, but
    computed from actual dates rather than assumed.
    """

    feature_rows: list = []
    metadata_rows: list = []
    target_rows: list = []

    for participant_id in participant_ids:
        dates = _participant_dates(session, participant_id)
        windows = compute_valid_windows(participant_id, dates, config.window_size_days)

        for window in windows:
            fv = build_features(participant_id, window.target_date, session, config)

            feature_rows.append(dict(fv.features))
            metadata_rows.append(
                {
                    "participant_id": participant_id,
                    "target_date": fv.target_date,
                    "window_start": fv.window_start,
                    "window_end": fv.window_end,
                    "completeness": fv.completeness,
                    "missing_feature_count": len(fv.missing_features),
                    "missing_features": ",".join(fv.missing_features),
                    "tier_1_missing": fv.tier_missing_counts.get("tier_1", 0),
                    "tier_2_missing": fv.tier_missing_counts.get("tier_2", 0),
                    "tier_3_missing": fv.tier_missing_counts.get("tier_3", 0),
                }
            )

            target_sin, target_cos = (
                clock_to_sincos(fv.target_dlmo_hour) if fv.target_dlmo_hour is not None else (None, None)
            )
            target_rows.append(
                {
                    "participant_id": participant_id,
                    "target_date": fv.target_date,
                    "target_dlmo_hour": fv.target_dlmo_hour,
                    "target_dlmo_sin": target_sin,
                    "target_dlmo_cos": target_cos,
                }
            )

    X = pd.DataFrame(feature_rows, columns=list(FEATURE_NAMES))
    metadata = pd.DataFrame(metadata_rows)
    targets = pd.DataFrame(target_rows)

    return FeatureDataset(X=X, feature_names=FEATURE_NAMES, metadata=metadata, targets=targets)


def build_feature_dataset_for_all_participants(
    session: Session, config: FeatureConfig = DEFAULT_FEATURE_CONFIG
) -> FeatureDataset:
    participant_ids = list(session.execute(select(Participant.id).order_by(Participant.id)).scalars().all())
    return build_feature_dataset(participant_ids, session, config)
