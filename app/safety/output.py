"""The safe output contract -- the one structured object this layer
produces. No UI markup, no free-form text generation; every string
field is either a fixed message (``app.safety.messages``) or a plain
number/label."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.safety.enums import STATUS_FLAGGED, STATUS_INSUFFICIENT_DATA, STATUS_OK
from app.safety.messages import BOUNDARY_NOTE_SHORT, INSUFFICIENT_DATA_GUIDANCE, NON_DIAGNOSTIC_STATEMENT


@dataclass(frozen=True)
class ActiveSafetyFlag:
    flag_type: str
    severity: str
    lifecycle_state: str
    message: str
    first_detected_date: Optional[object]
    triggering_statistics: dict


@dataclass(frozen=True)
class SafeOutput:
    prediction_available: bool
    dlmo_hour: Optional[float]
    confidence_score: Optional[float]
    confidence_label: Optional[str]
    display_precision: str

    alignment_score: Optional[float]

    recommendation_available: bool
    recommendation_suppressed: bool
    recommendation_text: Optional[str]

    active_safety_flags: list
    highest_safety_severity: Optional[str]

    boundary_note: str
    non_diagnostic_statement: Optional[str]
    qualifier_message: Optional[str]

    status: str
    required_action: Optional[str]

    audit_metadata: dict = field(default_factory=dict)


def insufficient_data_output(audit_metadata: dict) -> SafeOutput:
    return SafeOutput(
        prediction_available=False, dlmo_hour=None, confidence_score=audit_metadata.get("confidence_score"),
        confidence_label=None, display_precision="NONE", alignment_score=None,
        recommendation_available=False, recommendation_suppressed=False, recommendation_text=None,
        active_safety_flags=[], highest_safety_severity=None,
        boundary_note=BOUNDARY_NOTE_SHORT, non_diagnostic_statement=None, qualifier_message=INSUFFICIENT_DATA_GUIDANCE,
        status=STATUS_INSUFFICIENT_DATA, required_action="complete_more_data", audit_metadata=audit_metadata,
    )
