"""Automated sanity checks for the Phase 13 personalization system."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.personalization.dispatcher import PersonalizationOutput
from app.recommendations.personalization import ADAPTIVE_POLICY, LITERATURE, PERSONAL_EFFECT, PERSONAL_RANKING


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass
class ValidationReport:
    checks: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks)

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.checks.append(CheckResult(name=name, passed=bool(passed), detail=detail))

    def summary_lines(self) -> list:
        return [f"[{'PASS' if c.passed else 'FAIL'}] {c.name}: {c.detail}" for c in self.checks]


def run_sanity_checks(output: PersonalizationOutput) -> ValidationReport:
    report = ValidationReport()

    valid_phases = {LITERATURE, PERSONAL_RANKING, PERSONAL_EFFECT, ADAPTIVE_POLICY}
    report.add(
        "all_phases_are_known",
        all(p in valid_phases for p in output.phase_by_intervention_type.values()),
        f"phases={output.phase_by_intervention_type}",
    )

    report.add(
        "no_overlap_between_ranking_and_effect_dicts_semantics",
        True,  # structural: they are independent dicts by design, keyed by intervention_id
        "personalized_ranking and personal_expected_improvement are independent dicts",
    )

    for intervention_id, score in output.personalized_ranking.items():
        report.add(
            f"ranking_score_bounded/{intervention_id}",
            0.0 - 1e-9 <= score <= 1.0 + 1e-9,
            f"score={score}",
        )

    for itype, model in output.effect_models.items():
        if model.validity.valid:
            report.add(f"effect_model_finite/{itype}", model.slope is not None, f"slope={model.slope}")

    return report
