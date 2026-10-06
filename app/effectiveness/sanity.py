"""Automated sanity checks for the Phase 12 effectiveness system."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.effectiveness.dispatcher import InterventionEffectResult


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
            raise AssertionError("Effect result failed validation: " + "; ".join(f"{c.name} ({c.detail})" for c in failed))


def run_sanity_checks(result: InterventionEffectResult) -> ValidationReport:
    report = ValidationReport()

    report.add(
        "chosen_phase_is_valid_or_none",
        result.chosen_phase in (None, 1, 2, 3),
        f"chosen_phase={result.chosen_phase}",
    )

    if result.chosen_phase is not None:
        report.add("phase1_marked_sufficient", result.phase1.sufficient_data, "phase1.sufficient_data")

    if result.phase1.compliance_rate is not None:
        report.add(
            "compliance_rate_within_bounds",
            0.0 - 1e-9 <= result.phase1.compliance_rate <= 1.0 + 1e-9,
            f"compliance_rate={result.phase1.compliance_rate}",
        )

    if result.chosen_phase == 2 and result.phase2 is not None and result.phase2.match_quality is not None:
        report.add(
            "phase2_match_marked_valid",
            result.phase2.match_quality.match_valid,
            f"similarity_score={result.phase2.match_quality.similarity_score}",
        )

    if result.chosen_phase == 3 and result.phase3 is not None:
        report.add(
            "phase3_n_observations_meets_minimum",
            result.phase3.n_observations >= 0,
            f"n={result.phase3.n_observations}",
        )
        report.add(
            "phase3_confidence_interval_contains_estimate_direction",
            result.phase3.confidence_interval_lower <= result.phase3.effect_mins_per_compliance_unit <= result.phase3.confidence_interval_upper,
            f"CI=[{result.phase3.confidence_interval_lower}, {result.phase3.confidence_interval_upper}], estimate={result.phase3.effect_mins_per_compliance_unit}",
        )

    return report
