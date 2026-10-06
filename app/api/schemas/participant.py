from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from app.api.schemas.common import BOUNDARY_NOTE


class ParticipantResponse(BaseModel):
    participant_id: int
    participant_code: str
    chronotype: Optional[str] = Field(default=None, description="Intrinsic chronotype category.")
    estimated_biological_clock: Optional[str] = Field(
        default=None, description="Current estimated biological clock, HH:MM (24h). Not a clinical measurement."
    )
    adapted_biological_clock: Optional[str] = Field(default=None, description="Slower-moving behavioral-equilibrium estimate, HH:MM.")
    current_alignment_score: Optional[float] = None
    status: str = Field(description="Enrollment/onboarding status.")
    enrollment_date: date
    boundary_note: str = BOUNDARY_NOTE
