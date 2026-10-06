"""Phase 3: longitudinal regression-controlled personal-effect
estimation.

**Labeled REGRESSION_CONTROLLED_ESTIMATE** -- stronger than Phases 1-2
because it controls for several concurrent behavioral covariates in
one model rather than comparing two raw period means, but still an
observational regression on one participant's own data, not a
randomized experiment; "estimated effect", never "proven" or "clinical
effect".

Uses ``sklearn.linear_model.LinearRegression`` -- a simple,
interpretable model, per the brief's explicit instruction not to reach
for something more complex. Standard errors/confidence intervals are
not provided by scikit-learn's regressor, so they are computed here
via the standard OLS sampling-covariance formula
(``MSE * (X^T X)^-1``), a well-established textbook result, not a
custom/ad-hoc approximation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_cls
from typing import Optional

import numpy as np
from scipy import stats
from sklearn.linear_model import LinearRegression

from app.effectiveness.config import DEFAULT_EFFECTIVENESS_CONFIG, EffectivenessConfig, REGRESSION_CONTROLLED_ESTIMATE
from app.effectiveness.outcomes import dlmo_change_minutes
from app.effectiveness.phase1 import DayRecord
from app.synthetic.time_utils import circular_diff_hours

INSUFFICIENT_DATA = "insufficient_data"

# Non-target covariates included alongside compliance_degree. Clock-hour
# signals are used as plain floats -- valid here for the same reason
# Phase 8's meal-timing component documents: these signals cluster well
# away from the midnight wrap point in practice, so a naive float does
# not introduce a discontinuity artifact.
_COVARIATE_SIGNALS = ("morning_light", "meal_timing", "exercise")


@dataclass(frozen=True)
class InterventionEffectPhase3:
    intervention_id: int
    participant_id: int

    effect_mins_per_compliance_unit: Optional[float]
    confidence_interval_lower: Optional[float]
    confidence_interval_upper: Optional[float]
    standard_error: Optional[float]
    r_squared: Optional[float]
    n_observations: int
    residual_diagnostics: Optional[dict]
    coefficients: Optional[dict]  # covariate name -> coefficient, for auditability

    measurement_phase: int
    interpretation: str

    sufficient_data: bool
    insufficiency_reason: Optional[str] = None


def _insufficient(intervention_id: int, participant_id: int, n_observations: int, reason: str) -> InterventionEffectPhase3:
    return InterventionEffectPhase3(
        intervention_id=intervention_id, participant_id=participant_id,
        effect_mins_per_compliance_unit=None, confidence_interval_lower=None, confidence_interval_upper=None,
        standard_error=None, r_squared=None, n_observations=n_observations, residual_diagnostics=None,
        coefficients=None, measurement_phase=3, interpretation=REGRESSION_CONTROLLED_ESTIMATE,
        sufficient_data=False, insufficiency_reason=reason,
    )


def _build_design_matrix(sorted_dates: list, records: dict, baseline_dlmo_reference: float) -> tuple:
    """One row per day with a complete covariate set and a defined
    previous-day DLMO change; days with any missing value are excluded
    entirely rather than imputed (a regression input must never be
    fabricated)."""

    rows = []
    y = []
    for i in range(1, len(sorted_dates)):
        today, yesterday = sorted_dates[i], sorted_dates[i - 1]
        today_rec, yest_rec = records.get(today), records.get(yesterday)
        if today_rec is None or yest_rec is None:
            continue
        if today_rec.dlmo_hour is None or yest_rec.dlmo_hour is None:
            continue
        if today_rec.compliance_degree is None:
            continue

        covariates = [today_rec.signal_values.get(s) for s in _COVARIATE_SIGNALS]
        if any(c is None for c in covariates):
            continue

        prev_dlmo_deviation = circular_diff_hours(yest_rec.dlmo_hour, baseline_dlmo_reference) * 60.0
        change = dlmo_change_minutes(yest_rec.dlmo_hour, today_rec.dlmo_hour)
        if change is None:
            continue

        rows.append([today_rec.compliance_degree, *covariates, prev_dlmo_deviation])
        y.append(change)

    return rows, y


def evaluate_phase3_effect(
    intervention_id: int,
    participant_id: int,
    records: dict,  # date -> DayRecord, the participant's full available history for this intervention type
    baseline_dlmo_reference: float,
    config: EffectivenessConfig = DEFAULT_EFFECTIVENESS_CONFIG,
) -> InterventionEffectPhase3:
    sorted_dates = sorted(records.keys())
    rows, y_list = _build_design_matrix(sorted_dates, records, baseline_dlmo_reference)
    n = len(rows)

    if n < config.min_regression_observations:
        return _insufficient(intervention_id, participant_id, n, INSUFFICIENT_DATA)

    X = np.array(rows, dtype=float)
    y = np.array(y_list, dtype=float)
    column_names = ("compliance_degree", *_COVARIATE_SIGNALS, "prev_dlmo_deviation")

    model = LinearRegression()
    model.fit(X, y)
    r_squared = float(model.score(X, y))

    design = np.column_stack([np.ones(n), X])
    p = design.shape[1]
    dof = n - p
    if dof <= 0:
        return _insufficient(intervention_id, participant_id, n, INSUFFICIENT_DATA)

    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    residuals = y - design @ beta
    mse = float(np.sum(residuals ** 2) / dof)

    try:
        cov_beta = mse * np.linalg.pinv(design.T @ design)
    except np.linalg.LinAlgError:
        return _insufficient(intervention_id, participant_id, n, INSUFFICIENT_DATA)

    se = np.sqrt(np.clip(np.diag(cov_beta), 0.0, None))
    t_crit = float(stats.t.ppf(1.0 - (1.0 - config.confidence_level) / 2.0, dof))

    compliance_index = 1  # beta[0] is the intercept
    compliance_coef = float(beta[compliance_index])
    compliance_se = float(se[compliance_index])
    ci_lower = compliance_coef - t_crit * compliance_se
    ci_upper = compliance_coef + t_crit * compliance_se

    coefficients = {"intercept": float(beta[0])}
    coefficients.update({name: float(beta[i + 1]) for i, name in enumerate(column_names)})

    return InterventionEffectPhase3(
        intervention_id=intervention_id,
        participant_id=participant_id,
        effect_mins_per_compliance_unit=compliance_coef,
        confidence_interval_lower=ci_lower,
        confidence_interval_upper=ci_upper,
        standard_error=compliance_se,
        r_squared=r_squared,
        n_observations=n,
        residual_diagnostics={
            "residual_std": float(np.std(residuals)),
            "max_abs_residual": float(np.max(np.abs(residuals))),
            "degrees_of_freedom": dof,
        },
        coefficients=coefficients,
        measurement_phase=3,
        interpretation=REGRESSION_CONTROLLED_ESTIMATE,
        sufficient_data=True,
    )
