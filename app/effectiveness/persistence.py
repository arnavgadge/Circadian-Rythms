"""Persisting a computed effect evaluation to
``intervention_effect_estimates``.

Always **inserts** a new row -- an old estimate is never overwritten,
so the full history of how an estimate evolved as more data arrived
remains auditable (see docs "Recomputation"). This module performs no
computation of its own; the caller must have already run
``app.effectiveness.dispatcher.evaluate_intervention_effect``.
"""

from __future__ import annotations

import dataclasses

from sqlalchemy.orm import Session

from app.database.models import InterventionEffectEstimate
from app.effectiveness.config import DEFAULT_EFFECTIVENESS_CONFIG, EffectivenessConfig
from app.effectiveness.dispatcher import InterventionEffectResult


def persist_effect_estimate(
    session: Session,
    participant_id: int,
    recommendation_id: int,
    result: InterventionEffectResult,
    config: EffectivenessConfig = DEFAULT_EFFECTIVENESS_CONFIG,
) -> InterventionEffectEstimate:
    chosen = result.chosen_phase

    if chosen is None:
        p1 = result.phase1
        row = InterventionEffectEstimate(
            participant_id=participant_id, recommendation_id=recommendation_id,
            measurement_phase=1, interpretation=p1.interpretation,
            period_start=None, period_end=None,
            effect_estimate=None, confidence_interval_lower=None, confidence_interval_upper=None,
            standard_error=None, r_squared=None,
            n_observations=p1.observed_days, compliance_rate=p1.compliance_rate, confound_flag=False,
            methodology_version=config.effectiveness_config_version, model_version=None,
            diagnostics={"insufficiency_reason": p1.insufficiency_reason},
        )
    elif chosen == 1:
        p1 = result.phase1
        row = InterventionEffectEstimate(
            participant_id=participant_id, recommendation_id=recommendation_id,
            measurement_phase=1, interpretation=p1.interpretation,
            period_start=None, period_end=None,
            effect_estimate=p1.effect_estimate, confidence_interval_lower=None, confidence_interval_upper=None,
            standard_error=None, r_squared=None,
            n_observations=p1.observed_days, compliance_rate=p1.compliance_rate, confound_flag=p1.confound_flag,
            methodology_version=config.effectiveness_config_version, model_version=None,
            diagnostics={
                "baseline_dlmo": p1.baseline_dlmo, "recent_dlmo": p1.recent_dlmo,
                "alignment_change": p1.alignment_change,
                "confound_changed_signals": p1.confound_report.changed_signals if p1.confound_report else {},
            },
        )
    elif chosen == 2:
        p2 = result.phase2
        row = InterventionEffectEstimate(
            participant_id=participant_id, recommendation_id=recommendation_id,
            measurement_phase=2, interpretation=p2.interpretation,
            period_start=p2.match_quality.matched_period_start if p2.match_quality else None,
            period_end=p2.match_quality.matched_period_end if p2.match_quality else None,
            effect_estimate=p2.mean_dlmo_difference, confidence_interval_lower=None, confidence_interval_upper=None,
            standard_error=None, r_squared=None,
            n_observations=result.phase1.observed_days, compliance_rate=result.phase1.compliance_rate,
            confound_flag=result.phase1.confound_flag,
            methodology_version=config.effectiveness_config_version, model_version=None,
            diagnostics={
                "similarity_score": p2.match_quality.similarity_score if p2.match_quality else None,
                "variables_matched": list(p2.match_quality.variables_matched) if p2.match_quality else [],
                "slope_difference": p2.slope_difference,
                "mean_alignment_difference": p2.mean_alignment_difference,
            },
        )
    else:  # chosen == 3
        p3 = result.phase3
        row = InterventionEffectEstimate(
            participant_id=participant_id, recommendation_id=recommendation_id,
            measurement_phase=3, interpretation=p3.interpretation,
            period_start=None, period_end=None,
            effect_estimate=p3.effect_mins_per_compliance_unit,
            confidence_interval_lower=p3.confidence_interval_lower, confidence_interval_upper=p3.confidence_interval_upper,
            standard_error=p3.standard_error, r_squared=p3.r_squared,
            n_observations=p3.n_observations, compliance_rate=result.phase1.compliance_rate,
            confound_flag=result.phase1.confound_flag,
            methodology_version=config.effectiveness_config_version, model_version="linear_regression_v1",
            diagnostics={"coefficients": p3.coefficients, "residual_diagnostics": p3.residual_diagnostics},
        )

    session.add(row)
    session.flush()
    return row
