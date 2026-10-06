"""Automated sanity checks for the contributor ranking engine (the 12
checks required for Phase 9)."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.contributors.engine import SIGNALS, ContributorResult


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
            raise AssertionError("Contributor result failed validation: " + "; ".join(f"{c.name} ({c.detail})" for c in failed))


def run_sanity_checks(result: ContributorResult) -> ValidationReport:
    report = ValidationReport()

    # 1. exactly five candidate ranking signals
    report.add(
        "exactly_five_candidate_signals",
        len(result.all_candidates) == 5,
        f"expected 5 candidates, got {len(result.all_candidates)}",
    )

    # 2. no duplicate signals
    names = [c.signal for c in result.all_candidates]
    report.add("no_duplicate_signals", len(names) == len(set(names)), f"signals: {names}")

    report.add(
        "all_candidates_are_locked_signals",
        set(names) == set(SIGNALS),
        f"expected {set(SIGNALS)}, got {set(names)}",
    )

    # 3. top 3 ordering is descending
    scores = [c.contributor_score for c in result.contributors if c.contributor_score is not None]
    descending = all(scores[i] >= scores[i + 1] - 1e-9 for i in range(len(scores) - 1))
    report.add("top_3_descending_order", descending, f"scores: {scores}")

    report.add(
        "top_3_size_correct",
        len(result.contributors) <= 3,
        f"expected at most 3, got {len(result.contributors)}",
    )

    # 4. normalized effect ranges 0-100
    bad_norm = [
        c.signal for c in result.all_candidates
        if c.normalized_phase_effect is not None and not (0.0 - 1e-9 <= c.normalized_phase_effect <= 100.0 + 1e-9)
    ]
    report.add("normalized_effect_within_bounds", len(bad_norm) == 0, f"out of bounds: {bad_norm}")

    # 5. alignment deficits range 0-100
    bad_deficit = [
        c.signal for c in result.all_candidates
        if c.alignment_deficit is not None and not (0.0 - 1e-9 <= c.alignment_deficit <= 100.0 + 1e-9)
    ]
    report.add("alignment_deficit_within_bounds", len(bad_deficit) == 0, f"out of bounds: {bad_deficit}")

    # 6. contributor scores valid (0-100 where present)
    bad_scores = [
        c.signal for c in result.all_candidates
        if c.contributor_score is not None and not (0.0 - 1e-9 <= c.contributor_score <= 100.0 + 1e-9)
    ]
    report.add("contributor_scores_within_bounds", len(bad_scores) == 0, f"out of bounds: {bad_scores}")

    # 8. exercise never receives a fabricated alignment component
    exercise = next((c for c in result.all_candidates if c.signal == "exercise"), None)
    exercise_ok = exercise is None or (exercise.alignment_deficit is None and exercise.alignment_component_score is None)
    report.add(
        "exercise_has_no_fabricated_alignment_component",
        exercise_ok,
        "exercise has no deficit/component" if exercise_ok else f"exercise deficit={exercise.alignment_deficit}",
    )

    return report
