from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.api.schemas.status import ContributorSummary


class ContributorsResponse(BaseModel):
    participant_id: int
    target_date: Optional[str] = None
    contributors: list = Field(default_factory=list, description="Modeled influence, ranked -- never a proven cause.")
    note: str = "Contributors reflect modeled influence within CircadianIQ, not a proven physiological cause."
