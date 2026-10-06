"""The recommendation engine: ``select_recommendations()``.

Converts Phase 9's ranked contributors into exactly **1 primary
intervention + up to 2 supporting nudges** -- never three
equal-priority recommendations. Deterministic: no LLM, no free-form
generation, no hidden randomness. Every candidate intervention comes
from the database catalogue (``app.recommendations.catalogue``); this
module only scores and selects among them.

Pipeline per candidate:

1. filter (active, severity-applicable, not a duplicate intervention id)
2. resolve contributor relevance (Phase 9's top-3 ranked, significant
   contributors only -- reduced when the matched signal's data is
   imputed)
3. resolve current behavior value; drop the candidate if unavailable
   rather than fabricate one
4. compute the graduated target (halfway to the desired value, bound-
   and direction-clamped)
5. compute feasibility (baseline + compliance history + target
   difficulty)
6. resolve expected improvement via the active personalization phase
7. score := relevance * (impact_weight*norm_impact + feasibility_weight*norm_feasibility)
            + personalization_adjustment + continuation_bonus

Then: pick the single best (cooldown-aware) candidate as primary,
drop conflicting/redundant candidates, and take up to two of what
remains as supporting nudges.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_cls
from typing import Optional

from app.recommendations.behavior import resolve_current_value
from app.recommendations.catalogue import CandidateIntervention, applies_to_severity
from app.recommendations.config import DEFAULT_RECOMMENDATION_CONFIG, RecommendationConfig
from app.recommendations.cooldown import continuation_bonus_for, should_continue_prior_primary
from app.recommendations.feasibility import compute_feasibility
from app.recommendations.inputs import RecommendationInputs
from app.recommendations.personalization import resolve_expected_improvement
from app.recommendations.relevance import compute_contributor_relevance
from app.recommendations.scoring import compute_candidate_score, normalize_max_scale
from app.recommendations.severity import classify_severity, severity_weights
from app.recommendations.targets import GraduatedTarget, compute_graduated_target
from app.recommendations.templates import render_template

PRIMARY_PRIORITY = 1


@dataclass(frozen=True)
class CandidateDiagnostic:
    intervention_id: int
    intervention_code: str
    contributor_relevance: float
    matched_signals: tuple
    normalized_expected_impact: Optional[float]
    feasibility_score: Optional[float]
    personalization_adjustment: float
    continuation_bonus: float
    candidate_score: Optional[float]
    excluded: bool
    exclusion_reason: Optional[str]


@dataclass(frozen=True)
class SelectedRecommendation:
    intervention_id: int
    intervention_code: str
    intervention_type: str
    priority: int
    contributor_signal: Optional[str]
    current_value: float
    target_value: float
    target_unit: str
    text: str
    expected_improvement_minutes: Optional[float]
    expected_improvement_source: str
    impact_score: float
    feasibility_score: float
    candidate_score: float
    graduated_target: GraduatedTarget


@dataclass(frozen=True)
class RecommendationResult:
    primary: Optional[SelectedRecommendation]
    supporting: list
    severity: str
    personalization_phase: str
    selection_version: str
    diagnostics: list


@dataclass
class _Evaluated:
    candidate: CandidateIntervention
    matched_signals: tuple
    current_value: float
    graduated_target: GraduatedTarget
    feasibility_score: float
    feasibility_basis: str
    expected_improvement_minutes: Optional[float]
    expected_improvement_source: str
    relevance: float
    personalization_adjustment: float


def _target_unit(value_kind: str) -> str:
    return {"clock_hour": "clock_time", "duration_minutes": "minutes", "duration_hours": "hours"}[value_kind]


def _significant_ranked_signals(contributor_result) -> tuple:
    return tuple(c.signal for c in contributor_result.contributors if c.significant)


def _data_quality_for_signal(contributor_result, signal: str) -> str:
    match = next((c for c in contributor_result.all_candidates if c.signal == signal), None)
    return match.data_quality if match is not None else "unavailable"


def _evaluate_candidate(
    candidate: CandidateIntervention,
    inputs: RecommendationInputs,
    ranked_signals: tuple,
    config: RecommendationConfig,
) -> tuple:
    """Returns ``(_Evaluated | None, exclusion_reason | None)``."""

    if not candidate.is_active:
        return None, "inactive"

    severity = classify_severity(inputs.alignment_result.final_score, config)
    if not applies_to_severity(candidate, severity):
        return None, "not_applicable_to_severity"

    relevance_result = compute_contributor_relevance(candidate.contributor_signals, ranked_signals, config)
    relevance = relevance_result.relevance
    if relevance_result.matched_signals:
        qualities = {_data_quality_for_signal(inputs.contributor_result, s) for s in relevance_result.matched_signals}
        if "unavailable" in qualities and len(qualities) == 1:
            relevance = 0.0
        elif "imputed" in qualities:
            relevance *= config.imputed_data_relevance_multiplier

    value_signal = relevance_result.matched_signals[0] if relevance_result.matched_signals else (
        candidate.contributor_signals[0] if candidate.contributor_signals else None
    )
    if value_signal is None:
        return None, "no_mapped_signal"

    current_value = resolve_current_value(value_signal, inputs.behavioral_history)
    if current_value is None:
        return None, "missing_behavioral_data"

    graduated_target = compute_graduated_target(
        candidate, current_value, inputs.alignment_result.ideal_sleep_onset_hour, config.graduated_target_fraction
    )

    shift_fraction = (
        min(1.0, abs(graduated_target.applied_shift) / candidate.max_shift_per_recommendation)
        if candidate.max_shift_per_recommendation > 0
        else 0.0
    )
    recent_compliance = inputs.recent_compliance_by_intervention.get(candidate.intervention_id, ())
    feasibility = compute_feasibility(candidate.baseline_feasibility, shift_fraction, recent_compliance, config)

    personalization = resolve_expected_improvement(
        candidate.intervention_id,
        candidate.literature_expected_improvement_minutes,
        inputs.personalization_phase,
        inputs.personalized_ranking,
        inputs.personal_expected_improvement,
        config,
    )

    return (
        _Evaluated(
            candidate=candidate,
            matched_signals=relevance_result.matched_signals,
            current_value=current_value,
            graduated_target=graduated_target,
            feasibility_score=feasibility.score,
            feasibility_basis=feasibility.basis,
            expected_improvement_minutes=personalization.expected_improvement_minutes,
            expected_improvement_source=personalization.expected_improvement_source,
            relevance=relevance,
            personalization_adjustment=personalization.score_adjustment,
        ),
        None,
    )


def _to_selected(evaluated: _Evaluated, priority: int, normalized_impact: float, candidate_score: float, config) -> SelectedRecommendation:
    candidate = evaluated.candidate
    text = render_template(
        candidate, evaluated.graduated_target.target_value, evaluated.current_value,
        evaluated.expected_improvement_minutes if evaluated.expected_improvement_minutes is not None else 0.0,
    )
    return SelectedRecommendation(
        intervention_id=candidate.intervention_id,
        intervention_code=candidate.intervention_code,
        intervention_type=candidate.intervention_type,
        priority=priority,
        contributor_signal=evaluated.matched_signals[0] if evaluated.matched_signals else None,
        current_value=evaluated.current_value,
        target_value=evaluated.graduated_target.target_value,
        target_unit=_target_unit(candidate.value_kind),
        text=text,
        expected_improvement_minutes=evaluated.expected_improvement_minutes,
        expected_improvement_source=evaluated.expected_improvement_source,
        impact_score=normalized_impact,
        feasibility_score=evaluated.feasibility_score,
        candidate_score=candidate_score,
        graduated_target=evaluated.graduated_target,
    )


def _conflicts_with_primary(evaluated: _Evaluated, primary: _Evaluated) -> bool:
    if evaluated.candidate.intervention_id == primary.candidate.intervention_id:
        return True
    # Fully redundant: addresses exactly the same contributor signal(s)
    # as the primary and offers nothing new.
    return bool(evaluated.matched_signals) and set(evaluated.matched_signals) <= set(primary.matched_signals)


def select_recommendations(
    inputs: RecommendationInputs, config: RecommendationConfig = DEFAULT_RECOMMENDATION_CONFIG
) -> RecommendationResult:
    severity = classify_severity(inputs.alignment_result.final_score, config)
    weights = severity_weights(severity, config)
    ranked_signals = _significant_ranked_signals(inputs.contributor_result)
    today = inputs.today or date_cls.today()

    seen_ids: set = set()
    evaluations: list = []
    diagnostics: list = []

    for candidate in inputs.candidate_interventions:
        if candidate.intervention_id in seen_ids:
            diagnostics.append(
                CandidateDiagnostic(
                    candidate.intervention_id, candidate.intervention_code, 0.0, (), None, None, 0.0, 0.0, None,
                    True, "duplicate_intervention_id",
                )
            )
            continue
        seen_ids.add(candidate.intervention_id)

        evaluated, reason = _evaluate_candidate(candidate, inputs, ranked_signals, config)
        if evaluated is None:
            diagnostics.append(
                CandidateDiagnostic(
                    candidate.intervention_id, candidate.intervention_code, 0.0, (), None, None, 0.0, 0.0, None,
                    True, reason,
                )
            )
            continue
        evaluations.append(evaluated)

    if not evaluations:
        return RecommendationResult(None, [], severity, inputs.personalization_phase, config.recommendation_config_version, diagnostics)

    impact_magnitudes = {
        e.candidate.intervention_id: (abs(e.expected_improvement_minutes) if e.expected_improvement_minutes is not None else None)
        for e in evaluations
    }
    normalized_impacts = normalize_max_scale(impact_magnitudes)

    scored: list = []
    for evaluated in evaluations:
        normalized_impact = normalized_impacts.get(evaluated.candidate.intervention_id) or 0.0
        continuation = continuation_bonus_for(evaluated.candidate.intervention_id, inputs.prior_primary, today, config)
        score = compute_candidate_score(
            evaluated.relevance, normalized_impact, evaluated.feasibility_score,
            weights.impact_weight, weights.feasibility_weight,
            evaluated.personalization_adjustment, continuation,
        )
        scored.append((evaluated, normalized_impact, score, continuation))
        diagnostics.append(
            CandidateDiagnostic(
                evaluated.candidate.intervention_id, evaluated.candidate.intervention_code,
                evaluated.relevance, evaluated.matched_signals, normalized_impact, evaluated.feasibility_score,
                evaluated.personalization_adjustment, continuation, score.candidate_score, False, None,
            )
        )

    eligible = [s for s in scored if s[0].relevance >= config.min_relevance_threshold]
    pool = eligible if eligible else scored  # fallback: no signal-specific match found anywhere
    pool.sort(key=lambda s: s[2].candidate_score, reverse=True)

    best_evaluated, best_impact, best_score, _ = pool[0]
    primary_tuple = pool[0]
    if inputs.prior_primary is not None:
        prior_match = next(
            (s for s in pool if s[0].candidate.intervention_id == inputs.prior_primary.intervention_id), None
        )
        if prior_match is not None and prior_match is not primary_tuple:
            if should_continue_prior_primary(prior_match[2].candidate_score, best_score.candidate_score, config):
                primary_tuple = prior_match

    primary_evaluated, primary_impact, primary_score, _ = primary_tuple
    primary = _to_selected(primary_evaluated, PRIMARY_PRIORITY, primary_impact, primary_score.candidate_score, config)

    remaining = [s for s in pool if not _conflicts_with_primary(s[0], primary_evaluated)]
    remaining.sort(key=lambda s: s[2].candidate_score, reverse=True)

    supporting = []
    for priority, (evaluated, impact, score, _) in enumerate(remaining[: config.max_supporting_recommendations], start=2):
        supporting.append(_to_selected(evaluated, priority, impact, score.candidate_score, config))

    return RecommendationResult(
        primary=primary,
        supporting=supporting,
        severity=severity,
        personalization_phase=inputs.personalization_phase,
        selection_version=config.recommendation_config_version,
        diagnostics=diagnostics,
    )
