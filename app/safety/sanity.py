"""Automated sanity checks for the Phase 14 safety layer."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.safety.enums import HIGH, MODERATE, STATUS_FLAGGED, STATUS_INSUFFICIENT_DATA, STATUS_OK
from app.safety.guardrails import scan_for_prohibited_language
from app.safety.output import SafeOutput


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


def run_sanity_checks(output: SafeOutput) -> ValidationReport:
    report = ValidationReport()

    report.add("status_is_known", output.status in (STATUS_OK, STATUS_FLAGGED, STATUS_INSUFFICIENT_DATA), f"status={output.status}")

    if output.status == STATUS_INSUFFICIENT_DATA:
        report.add("no_dlmo_when_insufficient", output.dlmo_hour is None, f"dlmo_hour={output.dlmo_hour}")
        report.add("prediction_unavailable", output.prediction_available is False, "")
    else:
        report.add("boundary_note_present", bool(output.boundary_note), "boundary_note")

    if output.highest_safety_severity == HIGH:
        report.add("high_severity_suppresses_recommendation", output.recommendation_suppressed is True, "")

    found = scan_for_prohibited_language(
        output.boundary_note, output.recommendation_text, output.non_diagnostic_statement, output.qualifier_message,
        *[f.message for f in output.active_safety_flags],
    )
    report.add("no_prohibited_language", len(found) == 0, f"found={found}")

    return report
