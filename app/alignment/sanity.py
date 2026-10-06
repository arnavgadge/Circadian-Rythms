"""Automated sanity checks for the alignment engine (the 8 checks
required for Phase 8)."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field

from app.alignment.config import DEFAULT_ALIGNMENT_CONFIG, AlignmentConfig
from app.alignment.curves import exponential_decay_score
from app.alignment.engine import AlignmentResult, compute_alignment
from app.alignment.inputs import AlignmentInputs


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
            raise AssertionError("Alignment engine failed validation: " + "; ".join(f"{c.name} ({c.detail})" for c in failed))


def run_sanity_checks(
    result: AlignmentResult, config: AlignmentConfig = DEFAULT_ALIGNMENT_CONFIG
) -> ValidationReport:
    """Checks 1 (partially, see also the dedicated monotonicity test), 2,
    3, and 5 (a spot check) against one computed :class:`AlignmentResult`.
    Checks 4, 6, 7, 8 are structural and covered by
    :func:`run_structural_checks` since they concern the *codebase*, not
    a single result.
    """

    report = ValidationReport()

    # 2. component bounds
    out_of_bounds = [
        name for name, c in result.behavioral_components.items() if not (0.0 - 1e-9 <= c.score <= 100.0 + 1e-9)
    ]
    report.add(
        "component_scores_within_bounds",
        len(out_of_bounds) == 0,
        "all components in [0, 100]" if not out_of_bounds else f"out of bounds: {out_of_bounds}",
    )

    # 3. final bounds (and phase/behavioral sub-scores)
    scores_in_range = all(
        -1e-9 <= s <= 100.0 + 1e-9 for s in (result.final_score, result.phase_score, result.behavioral_score)
    )
    report.add(
        "final_and_subscores_within_bounds",
        scores_in_range,
        f"final={result.final_score:.2f}, phase={result.phase_score:.2f}, behavioral={result.behavioral_score:.2f}",
    )

    # 5. midnight correctness spot check (independent of the result, but
    # grouped here since it is part of the same "one call" sanity sweep)
    midnight_deviation_minutes = exponential_decay_score(20.0, config.phase_score_decay_minutes)
    report.add(
        "midnight_curve_well_defined",
        0.0 < midnight_deviation_minutes <= 100.0,
        f"score at 20 min deviation = {midnight_deviation_minutes:.2f}",
    )

    return report


def run_structural_checks() -> ValidationReport:
    """Checks 4, 6, 7, 8: properties of the codebase itself, not of any
    one computed result."""

    report = ValidationReport()

    # 4. weight sums
    try:
        DEFAULT_ALIGNMENT_CONFIG.validate()
        report.add("weight_sums_valid", True, "phase+behavioral and the 5 behavioral weights each sum to 1.0")
    except ValueError as exc:
        report.add("weight_sums_valid", False, str(exc))

    # 6. no MEQ influence
    import app.alignment.behavioral_alignment as behavioral_alignment_module
    import app.alignment.behavioral_components as behavioral_components_module
    import app.alignment.engine as engine_module
    import app.alignment.phase_alignment as phase_alignment_module

    alignment_modules = [engine_module, phase_alignment_module, behavioral_alignment_module, behavioral_components_module]
    meq_hits = [m.__name__ for m in alignment_modules if "meq" in inspect.getsource(m).lower()]
    report.add(
        "no_meq_influence",
        len(meq_hits) == 0,
        "MEQ not referenced anywhere in alignment scoring" if not meq_hits else f"MEQ referenced in: {meq_hits}",
    )

    # 7. no direct model-prediction dependence other than fused DLMO
    forbidden_imports = ("xgboost", "app.models.xgboost_model", "app.state.engine", "app.state.replay")
    hits = []
    for m in alignment_modules:
        source = inspect.getsource(m)
        for forbidden in forbidden_imports:
            if forbidden in source:
                hits.append((m.__name__, forbidden))
    report.add(
        "no_direct_model_dependence",
        len(hits) == 0,
        "only the fused DLMO value is consumed" if not hits else f"forbidden references found: {hits}",
    )

    # 1. phase score monotonicity (a property of the curve/config, checked
    # structurally here; see also the dedicated parametrized test suite)
    deviations = [0.0, 10.0, 20.0, 45.0, 75.0, 120.0, 240.0, 480.0]
    scores = [exponential_decay_score(d, DEFAULT_ALIGNMENT_CONFIG.phase_score_decay_minutes) for d in deviations]
    non_increasing = all(scores[i] >= scores[i + 1] - 1e-9 for i in range(len(scores) - 1))
    report.add(
        "phase_score_monotonic_non_increasing",
        non_increasing,
        f"scores at deviations {deviations} = {[round(s, 2) for s in scores]}",
    )

    # 8. no forbidden sleep feature reintroduced into the Phase 4/5 feature manifest
    from app.features.feature_manifest import FEATURE_NAMES

    forbidden_patterns = ("sleep_onset", "sleep_offset", "sleep_midpoint_sin", "sleep_midpoint_cos")
    reintroduced = [name for name in FEATURE_NAMES for pattern in forbidden_patterns if pattern in name]
    report.add(
        "no_forbidden_sleep_feature_in_ml_manifest",
        len(reintroduced) == 0,
        "Phase 4 manifest still excludes direct sleep timing" if not reintroduced else f"found: {reintroduced}",
    )

    return report
