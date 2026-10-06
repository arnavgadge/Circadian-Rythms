"""Layer 1: confidence gating.

**Reuses Phase 7's own confidence score and label** -- this module
computes nothing about confidence itself; it only maps
``app.fusion.config.ConfidenceLabel`` (already exactly the locked
HIGH >= 80 / MODERATE 60-80 / LOW 40-60 / NO_PREDICTION < 40 bands via
``DEFAULT_FUSION_CONFIG.confidence_label_thresholds = (80, 60, 40)``)
onto the display-precision metadata this layer is responsible for. The
Q25 no-prediction rules (all Tier-1 signals missing, <50% window
completeness, confidence < 40) are enforced once, inside
``app.fusion.fuse.fuse`` itself (``FusionResult.prediction_made``) --
this layer reads that outcome, it never re-derives or overrides it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.fusion.config import ConfidenceLabel
from app.safety.enums import APPROXIMATE, NONE_, NORMAL, NORMAL_WITH_QUALIFIER


@dataclass(frozen=True)
class ConfidenceGateResult:
    prediction_available: bool
    confidence_label: Optional[str]  # ConfidenceLabel.value, or None if no prediction at all
    confidence_score: Optional[float]
    display_precision: str


_DISPLAY_PRECISION_BY_LABEL = {
    ConfidenceLabel.HIGH: NORMAL,
    ConfidenceLabel.MODERATE: NORMAL_WITH_QUALIFIER,
    ConfidenceLabel.LOW: APPROXIMATE,
    ConfidenceLabel.NO_PREDICTION: NONE_,
}


def apply_confidence_gate(fusion_result) -> ConfidenceGateResult:
    """``fusion_result``: a ``app.fusion.fuse.FusionResult`` (or an
    object exposing the same ``prediction_made``/``fused_final``/
    ``final_confidence``/``confidence_label`` attributes). Never
    invoked with anything else -- there is exactly one confidence
    computation in the system, in Phase 7."""

    if not fusion_result.prediction_made or fusion_result.fused_final is None:
        return ConfidenceGateResult(False, None, fusion_result.final_confidence, NONE_)

    label = fusion_result.confidence_label
    if label == ConfidenceLabel.NO_PREDICTION:
        return ConfidenceGateResult(False, label.value, fusion_result.final_confidence, NONE_)

    return ConfidenceGateResult(
        prediction_available=True,
        confidence_label=label.value if hasattr(label, "value") else label,
        confidence_score=fusion_result.final_confidence,
        display_precision=_DISPLAY_PRECISION_BY_LABEL.get(label, APPROXIMATE),
    )
