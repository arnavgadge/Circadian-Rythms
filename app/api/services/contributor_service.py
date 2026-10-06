"""Application service for the current-contributors endpoint."""

from __future__ import annotations

from app.api.errors import NotFoundError
from app.api.repositories.circadian_repository import CircadianRepository
from app.api.schemas.contributors import ContributorsResponse
from app.api.schemas.status import ContributorSummary


class ContributorService:
    def __init__(self, repository: CircadianRepository):
        self.repository = repository

    def get_current(self, participant_id: int) -> ContributorsResponse:
        label = self.repository.get_latest(participant_id)
        if label is None:
            raise NotFoundError("No circadian result exists yet for this participant", detail=f"participant_id={participant_id}")

        rows = self.repository.get_contributors(label.id)
        contributors = [
            ContributorSummary(
                rank=row.rank, signal=row.contributor_signal, effect_minutes=row.effect_estimate,
                alignment_deficit=row.alignment_deficit, contributor_score=row.contributor_score,
                direction=row.direction, today_anomaly=row.today_anomaly,
            )
            for row in rows
        ]
        return ContributorsResponse(participant_id=participant_id, target_date=str(label.target_date), contributors=contributors)
