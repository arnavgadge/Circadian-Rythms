"""The Phase 11 pipeline diagnostic experiment: run daily inference
over a batch of synthetic participant/dates and summarize outcomes.

**No parameter is tuned from these results** -- every value used by
``run_daily_inference`` is the same locked, versioned configuration
used everywhere else; this module only observes and reports.

**Synthetic-data warning**: distributions here are properties of the
Phase 3 synthetic generator and the fixed synthetic seed used to run
this diagnostic, not evidence about real participants.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.pipeline.types import FAILED, INSUFFICIENT_HISTORY, NO_PREDICTION, SUCCESS


@dataclass
class BatchDiagnostics:
    n_runs: int
    successful: int
    insufficient_history: int
    no_prediction: int
    failed: int
    write_successes: int
    recommendations_generated: int
    average_runtime_seconds: float
    confidence_scores: list
    disagreement_regimes: dict
    alignment_scores: list


def summarize_batch(results: list) -> BatchDiagnostics:
    successful = sum(1 for r in results if r.status == SUCCESS)
    insufficient = sum(1 for r in results if r.status == INSUFFICIENT_HISTORY)
    no_prediction = sum(1 for r in results if r.status == NO_PREDICTION)
    failed = sum(1 for r in results if r.status == FAILED)
    write_successes = sum(1 for r in results if r.persistence_status in ("committed", "skipped"))
    recommendations = sum(1 for r in results if r.recommendation_result is not None and r.recommendation_result.primary is not None)

    confidence_scores = [
        r.fusion_result.final_confidence for r in results if r.fusion_result is not None and r.fusion_result.final_confidence is not None
    ]
    disagreement_regimes: dict = {}
    for r in results:
        if r.fusion_result is not None and r.fusion_result.disagreement_regime is not None:
            key = r.fusion_result.disagreement_regime.value
            disagreement_regimes[key] = disagreement_regimes.get(key, 0) + 1

    alignment_scores = [r.alignment_result.final_score for r in results if r.alignment_result is not None]
    runtimes = [r.runtime_seconds for r in results if r.runtime_seconds is not None]

    return BatchDiagnostics(
        n_runs=len(results),
        successful=successful,
        insufficient_history=insufficient,
        no_prediction=no_prediction,
        failed=failed,
        write_successes=write_successes,
        recommendations_generated=recommendations,
        average_runtime_seconds=(sum(runtimes) / len(runtimes)) if runtimes else 0.0,
        confidence_scores=confidence_scores,
        disagreement_regimes=disagreement_regimes,
        alignment_scores=alignment_scores,
    )


def report_dict(diag: BatchDiagnostics) -> dict:
    return {
        "n_runs": diag.n_runs,
        "successful": diag.successful,
        "insufficient_history": diag.insufficient_history,
        "no_prediction": diag.no_prediction,
        "failed": diag.failed,
        "write_success_rate": diag.write_successes / diag.n_runs if diag.n_runs else None,
        "recommendation_generation_rate": diag.recommendations_generated / diag.n_runs if diag.n_runs else None,
        "average_runtime_seconds": diag.average_runtime_seconds,
        "mean_confidence": (sum(diag.confidence_scores) / len(diag.confidence_scores)) if diag.confidence_scores else None,
        "disagreement_regime_distribution": diag.disagreement_regimes,
        "mean_alignment_score": (sum(diag.alignment_scores) / len(diag.alignment_scores)) if diag.alignment_scores else None,
    }
