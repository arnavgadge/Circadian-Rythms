"""Read access to ``circadian_labels`` / ``alignment_results`` /
``contributor_results``."""

from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import AlignmentResult, CircadianLabel, ContributorResult


class CircadianRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_latest(self, participant_id: int) -> Optional[CircadianLabel]:
        return self.session.execute(
            select(CircadianLabel)
            .where(CircadianLabel.participant_id == participant_id, CircadianLabel.is_latest.is_(True))
            .order_by(CircadianLabel.target_date.desc())
        ).scalars().first()

    def get_for_date(self, participant_id: int, target_date: date_type) -> Optional[CircadianLabel]:
        return self.session.execute(
            select(CircadianLabel).where(
                CircadianLabel.participant_id == participant_id,
                CircadianLabel.target_date == target_date,
                CircadianLabel.is_latest.is_(True),
            )
        ).scalars().first()

    def get_history(
        self, participant_id: int, start_date: Optional[date_type], end_date: Optional[date_type], limit: int
    ) -> list:
        stmt = select(CircadianLabel).where(CircadianLabel.participant_id == participant_id, CircadianLabel.is_latest.is_(True))
        if start_date is not None:
            stmt = stmt.where(CircadianLabel.target_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(CircadianLabel.target_date <= end_date)
        stmt = stmt.order_by(CircadianLabel.target_date.desc()).limit(limit)
        return list(self.session.execute(stmt).scalars().all())

    def get_contributors(self, circadian_label_id: int) -> list:
        alignment = self.session.execute(
            select(AlignmentResult).where(AlignmentResult.circadian_label_id == circadian_label_id)
        ).scalars().first()
        if alignment is None:
            return []
        return self.session.execute(
            select(ContributorResult).where(ContributorResult.alignment_result_id == alignment.id).order_by(ContributorResult.rank.asc())
        ).scalars().all()
