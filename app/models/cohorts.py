"""Attaches participant cohort labels (chronotype, personality) for
stratified evaluation.

Neither label is a model feature -- both are read from
``participant_profiles`` purely for post-hoc, diagnostic evaluation
grouping, never passed into ``X``.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import ParticipantProfile


def attach_participant_cohorts(metadata: pd.DataFrame, session: Session) -> pd.DataFrame:
    """Return a copy of ``metadata`` with ``chronotype`` and ``personality_key``
    columns added, joined on ``participant_id``."""

    participant_ids = metadata["participant_id"].unique().tolist()
    profiles = session.execute(
        select(ParticipantProfile).where(ParticipantProfile.participant_id.in_(participant_ids))
    ).scalars().all()

    rows = []
    for profile in profiles:
        personality_key = None
        if profile.synthetic_personality_profile:
            personality_key = profile.synthetic_personality_profile.get("personality")
        rows.append(
            {
                "participant_id": profile.participant_id,
                "chronotype": profile.chronotype_category,
                "personality_key": personality_key,
            }
        )
    cohort_df = pd.DataFrame(rows)

    return metadata.merge(cohort_df, on="participant_id", how="left")
