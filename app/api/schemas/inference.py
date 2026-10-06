from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from app.api.schemas.status import StatusResponse


class InferenceRequest(BaseModel):
    target_date: Optional[date] = Field(default=None, description="Defaults to today if omitted.")
    force_rerun: bool = Field(default=False, description="Explicit versioned rerun; bypasses the idempotency short-circuit.")


class InferenceResponse(BaseModel):
    participant_id: int
    target_date: date
    pipeline_status: str = Field(description="SUCCESS | INSUFFICIENT_HISTORY | NO_PREDICTION | FAILED")
    idempotent_short_circuit: bool = Field(description="True if an existing result was returned without recomputation.")
    persistence_status: str
    status: StatusResponse
