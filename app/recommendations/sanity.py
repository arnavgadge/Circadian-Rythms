"""Automated sanity checks for the recommendation engine."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.recommendations.engine import RecommendationResult


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

    def raise_if_failed(self) -> None:
        failed = [c for c in self.checks if not c.passed]
        if failed:
            raise AssertionError("Recommendation result failed validation: " + "; ".join(f"{c.name} ({c.detail})" for c in failed))


def run_sanity_checks(result: RecommendationResult) -> ValidationReport:
    report = ValidationReport()

    report.add(
        "at_most_one_primary",
        result.primary is None or result.primary.priority == 1,
        f"primary priority: {result.primary.priority if result.primary else None}",
    )

    report.add(
        "at_most_two_supporting",
        len(result.supporting) <= 2,
        f"supporting count: {len(result.supporting)}",
    )

    report.add(
        "supporting_priorities_are_2_and_3",
        [s.priority for s in result.supporting] == list(range(2, 2 + len(result.supporting))),
        f"priorities: {[s.priority for s in result.supporting]}",
    )

    ids = [result.primary.intervention_id] if result.primary else []
    ids += [s.intervention_id for s in result.supporting]
    report.add("no_duplicate_interventions", len(ids) == len(set(ids)), f"ids: {ids}")

    if result.primary is not None:
        report.add(
            "primary_impact_feasibility_scores_within_bounds",
            0.0 - 1e-9 <= result.primary.impact_score <= 1.0 + 1e-9
            and 0.0 - 1e-9 <= result.primary.feasibility_score <= 1.0 + 1e-9,
            f"impact={result.primary.impact_score}, feasibility={result.primary.feasibility_score}",
        )
        report.add(
            "primary_has_nonempty_text",
            bool(result.primary.text and result.primary.text.strip()),
            f"text={result.primary.text!r}",
        )

    for s in result.supporting:
        report.add(
            f"supporting_scores_within_bounds/{s.intervention_code}",
            0.0 - 1e-9 <= s.impact_score <= 1.0 + 1e-9 and 0.0 - 1e-9 <= s.feasibility_score <= 1.0 + 1e-9,
            f"impact={s.impact_score}, feasibility={s.feasibility_score}",
        )

    report.add(
        "severity_is_a_known_band",
        result.severity in ("good", "mild", "moderate", "severe"),
        f"severity={result.severity}",
    )

    return report
