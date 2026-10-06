"""The Phase 14 safety + confidence layer: ``SafetyEngine.evaluate()``.

    prediction -> confidence gate -> pattern detection -> safety decision -> safe output

Callable after Phase 11 daily inference and before any application/API/
UI output -- the one authoritative safety layer; no safety logic is
embedded anywhere else in the pipeline. Never modifies the underlying
fused DLMO, intrinsic DLMO, or any upstream model output -- it only
decides whether/how to *show* what upstream phases already computed.

Decision order (exactly as specified): validate prediction availability
-> confidence gate -> pattern detection -> highest severity -> validate
recommendation safety -> suppress if required -> construct output ->
record decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_cls
from typing import Optional

from sqlalchemy.orm import Session

from app.safety.catalogue_guard import validate_recommendation_safety
from app.safety.config import DEFAULT_SAFETY_CONFIG, SafetyConfig
from app.safety.confidence_gate import apply_confidence_gate
from app.safety.db_adapter import (
    apply_lifecycle_decision,
    load_open_flags,
    load_rolling_records,
    update_circadian_label_safety_metadata,
)
from app.safety.enums import DETECTED, HIGH, MODERATE, PERSISTING, RESOLVED, STATUS_FLAGGED, STATUS_INSUFFICIENT_DATA, STATUS_OK
from app.safety.lifecycle import reconcile_flag
from app.safety.messages import (
    BOUNDARY_NOTE_SHORT,
    HIGH_SEVERITY_SUPPRESSION_MESSAGE,
    NON_DIAGNOSTIC_STATEMENT,
    QUALIFIER_LOW,
    QUALIFIER_MODERATE,
)
from app.safety.output import ActiveSafetyFlag, SafeOutput, insufficient_data_output
from app.safety.patterns import (
    detect_continuous_drift,
    detect_low_alignment_despite_compliance,
    detect_persistent_early_phase,
    detect_persistent_late_phase,
)

_DETECTOR_BY_FLAG_TYPE = {
    "persistent_late_phase": detect_persistent_late_phase,
    "persistent_early_phase": detect_persistent_early_phase,
    "continuous_dlmo_drift": detect_continuous_drift,
    "low_alignment_despite_compliance": detect_low_alignment_despite_compliance,
}

_QUALIFIER_BY_PRECISION = {"NORMAL_WITH_QUALIFIER": QUALIFIER_MODERATE, "APPROXIMATE": QUALIFIER_LOW}


@dataclass(frozen=True)
class RecommendationInput:
    intervention_type: Optional[str]
    text: Optional[str]


class SafetyEngine:
    def __init__(self, config: SafetyConfig = DEFAULT_SAFETY_CONFIG):
        self.config = config

    def evaluate(
        self,
        session: Session,
        participant_id: int,
        as_of_date: date_cls,
        fusion_result,
        alignment_result=None,
        recommendation: Optional[RecommendationInput] = None,
        persist: bool = True,
    ) -> SafeOutput:
        # 1-2. Prediction availability + confidence gate.
        gate = apply_confidence_gate(fusion_result)

        if not gate.prediction_available:
            # Per the brief: never run pattern detection against an
            # obviously-unavailable prediction's own day; existing
            # flags are left exactly as they were.
            return insufficient_data_output({"confidence_score": gate.confidence_score, "as_of_date": str(as_of_date)})

        # 3. Pattern detection over the rolling history (never today's
        # own not-yet-evaluated day).
        records = load_rolling_records(session, participant_id, as_of_date, self.config)
        open_flags = load_open_flags(session, participant_id) if persist else {}

        decisions = []
        for flag_type, detector in _DETECTOR_BY_FLAG_TYPE.items():
            detection = detector(records, self.config)
            existing = open_flags.get(flag_type)
            resolution_check = None
            if existing is not None and not detection.triggering:
                trailing = records[-self.config.resolution_min_normal_observations :]
                resolution_check = detector(trailing, self.config)
            decision = reconcile_flag(detection, existing is not None, resolution_check, self.config)
            if decision is not None:
                decisions.append((decision, existing))

        # 8 (partial, done alongside 3 since it's the same detection
        # pass): persist each lifecycle decision.
        stored_rows = {}
        if persist:
            for decision, existing in decisions:
                row = apply_lifecycle_decision(session, participant_id, as_of_date, decision, existing, self.config)
                stored_rows[decision.flag_type] = row

        # 4. Highest severity among currently-active flags (DETECTED/PERSISTING only).
        active_decisions = [d for d, _ in decisions if d.lifecycle_state in (DETECTED, PERSISTING)]
        highest_severity = None
        if any(d.severity == HIGH for d in active_decisions):
            highest_severity = HIGH
        elif active_decisions:
            highest_severity = MODERATE

        active_flags = [
            ActiveSafetyFlag(
                flag_type=d.flag_type, severity=d.severity, lifecycle_state=d.lifecycle_state,
                message=_message_for(d.flag_type),
                first_detected_date=(stored_rows.get(d.flag_type).first_detected_date if stored_rows.get(d.flag_type) else as_of_date),
                triggering_statistics=d.triggering_statistics,
            )
            for d in active_decisions
        ]

        # 5-6. Recommendation safety validation + suppression.
        recommendation_available = False
        recommendation_suppressed = False
        recommendation_text = None

        if highest_severity == HIGH:
            recommendation_suppressed = True
            recommendation_text = HIGH_SEVERITY_SUPPRESSION_MESSAGE
        elif recommendation is not None:
            safety = validate_recommendation_safety(recommendation.intervention_type, recommendation.text, self.config)
            if safety.is_safe:
                recommendation_available = True
                recommendation_text = recommendation.text
            # An unsafe recommendation is blocked outright -- never shown, never a fallback message fabricated for it.

        # 7. Construct the safe structured output.
        status = STATUS_FLAGGED if active_flags else STATUS_OK
        output = SafeOutput(
            prediction_available=True,
            dlmo_hour=fusion_result.fused_final,
            confidence_score=gate.confidence_score,
            confidence_label=gate.confidence_label,
            display_precision=gate.display_precision,
            alignment_score=alignment_result.final_score if alignment_result is not None else None,
            recommendation_available=recommendation_available,
            recommendation_suppressed=recommendation_suppressed,
            recommendation_text=recommendation_text,
            active_safety_flags=active_flags,
            highest_safety_severity=highest_severity,
            boundary_note=BOUNDARY_NOTE_SHORT,
            non_diagnostic_statement=NON_DIAGNOSTIC_STATEMENT if active_flags else None,
            qualifier_message=_QUALIFIER_BY_PRECISION.get(gate.display_precision),
            status=status,
            required_action=("consider_professional_evaluation" if highest_severity == HIGH else None),
            audit_metadata={
                "as_of_date": str(as_of_date), "detection_version": self.config.safety_config_version,
                "n_flags_evaluated": len(decisions),
            },
        )

        # 8. Record the safety decision on the daily result too.
        if persist:
            update_circadian_label_safety_metadata(session, participant_id, as_of_date, status, recommendation_suppressed, highest_severity)

        return output


def _message_for(flag_type: str) -> str:
    from app.safety.messages import FLAG_MESSAGES

    return FLAG_MESSAGES[flag_type]
