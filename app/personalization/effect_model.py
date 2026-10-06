"""Phase 2: the personal effect model/curve.

    effect = slope * compliance + intercept

The coefficients are **consumed directly from Phase 12's Phase 3
regression** (``effect_mins_per_compliance_unit`` as the slope, its
own fitted intercept) -- this module never refits a second regression;
Phase 12 already produced exactly this line (compliance is one of its
covariates), so re-deriving it here would be a duplicated, and
possibly inconsistent, calculation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from app.personalization.config import DEFAULT_PERSONALIZATION_CONFIG, PersonalizationConfig
from app.personalization.validity import ModelValidityResult, check_model_validity

INSUFFICIENT = "insufficient"
PHASE3_REGRESSION = "phase3_regression"


@dataclass(frozen=True)
class PersonalEffectModelResult:
    intervention_type: str
    slope: Optional[float]
    intercept: Optional[float]
    r_squared: Optional[float]
    n_observations: int
    confidence_interval_lower: Optional[float]
    confidence_interval_upper: Optional[float]
    validity: ModelValidityResult
    evidence_source: str


def build_personal_effect_model(
    intervention_type: str,
    effect_estimate,  # app.database.models.InterventionEffectEstimate, phase 3, or None
    historical_compliance_degrees: Sequence,
    config: PersonalizationConfig = DEFAULT_PERSONALIZATION_CONFIG,
) -> PersonalEffectModelResult:
    if effect_estimate is None or effect_estimate.measurement_phase != 3 or effect_estimate.effect_estimate is None:
        return PersonalEffectModelResult(
            intervention_type=intervention_type, slope=None, intercept=None, r_squared=None,
            n_observations=0, confidence_interval_lower=None, confidence_interval_upper=None,
            validity=ModelValidityResult(False, ("no_phase3_estimate_available",)), evidence_source=INSUFFICIENT,
        )

    diagnostics = effect_estimate.diagnostics or {}
    intercept = (diagnostics.get("coefficients") or {}).get("intercept")
    slope = effect_estimate.effect_estimate
    n_observations = effect_estimate.n_observations or 0

    validity = check_model_validity(
        slope, intercept, effect_estimate.r_squared, n_observations,
        effect_estimate.confidence_interval_lower, effect_estimate.confidence_interval_upper,
        historical_compliance_degrees, config,
    )

    return PersonalEffectModelResult(
        intervention_type=intervention_type, slope=slope, intercept=intercept, r_squared=effect_estimate.r_squared,
        n_observations=n_observations, confidence_interval_lower=effect_estimate.confidence_interval_lower,
        confidence_interval_upper=effect_estimate.confidence_interval_upper, validity=validity,
        evidence_source=PHASE3_REGRESSION,
    )


def predict_effect(slope: Optional[float], intercept: Optional[float], compliance: Optional[float]) -> Optional[float]:
    """``effect = slope * compliance + intercept`` -- a point estimate,
    never presented as certain (see ``docs/personalization_engine.md``
    "Personal effect curve": callers should always show it alongside
    the model's own confidence interval, not alone)."""

    if slope is None or intercept is None or compliance is None:
        return None
    return slope * compliance + intercept
