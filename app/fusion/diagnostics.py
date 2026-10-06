"""The fusion diagnostic experiment: run fusion over an ordered set of
(XGBoost, state-engine) estimate pairs and summarize the result.

This module is pure computation over already-prepared rows -- it does
not load a model, query a database, or regenerate synthetic data
itself (see ``app/scripts/run_fusion_diagnostics.py`` for the
orchestration that assembles those inputs). Keeping it pure makes the
core fusion-over-a-sequence logic directly testable.

**Important scientific caveat**, repeated here because it materially
affects how to read this report: in the Phase 3 synthetic dataset, the
"state estimate" recomputed via state-engine replay is, by
construction, identical to the synthetic ground-truth target (Phase 3
generated that ground truth *using* the same state-transition model).
So a fused-error-vs-XGB-error comparison on this dataset mechanically
favors fusion -- one of its two inputs is effectively the answer key.
This experiment demonstrates that the fusion *mechanics* (weights,
disagreement handling, continuity, confidence) behave as designed, not
that fusion improves accuracy on real, independently-measured DLMO
data. See ``docs/dlmo_fusion.md`` "Scientific limitations".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from app.fusion.confidence import DataQualityInput
from app.fusion.config import DEFAULT_FUSION_CONFIG, DataQualityTier, FusionConfig
from app.fusion.fuse import fuse
from app.synthetic.time_utils import circular_diff_hours


@dataclass(frozen=True)
class FusionInputRow:
    """One test-set window's worth of estimates, ready to fuse.

    Rows for the same ``participant_id`` must be supplied in
    chronological ``target_date`` order -- :func:`run_fusion_over_windows`
    carries ``previous_fused_dlmo`` forward within a participant, reset
    at the start of each new participant.
    """

    participant_id: int
    target_date: object
    xgb_dlmo: Optional[float]
    state_dlmo: Optional[float]
    actual_dlmo: float
    data_quality: DataQualityInput


def run_fusion_over_windows(rows: list, config: FusionConfig = DEFAULT_FUSION_CONFIG) -> pd.DataFrame:
    """Run :func:`app.fusion.fuse.fuse` sequentially over ``rows``,
    grouped and ordered by participant, carrying the fused estimate
    forward as each participant's continuity anchor.
    """

    records = []
    previous_fused_by_participant: dict = {}

    for row in rows:
        previous_fused = previous_fused_by_participant.get(row.participant_id)
        result = fuse(row.xgb_dlmo, row.state_dlmo, previous_fused, row.data_quality, config)
        previous_fused_by_participant[row.participant_id] = result.fused_final

        xgb_error_minutes = (
            abs(circular_diff_hours(row.actual_dlmo, row.xgb_dlmo) * 60.0) if row.xgb_dlmo is not None else None
        )
        fused_error_minutes = (
            abs(circular_diff_hours(row.actual_dlmo, result.fused_final) * 60.0)
            if result.fused_final is not None
            else None
        )

        records.append(
            {
                "participant_id": row.participant_id,
                "target_date": row.target_date,
                "xgb_dlmo": row.xgb_dlmo,
                "state_dlmo": row.state_dlmo,
                "actual_dlmo": row.actual_dlmo,
                "fused_dlmo": result.fused_final,
                "disagreement_minutes": result.disagreement_minutes,
                "disagreement_regime": result.disagreement_regime.value if result.disagreement_regime else None,
                "xgb_final_weight": result.xgb_final_weight,
                "state_final_weight": result.state_final_weight,
                "continuity_applied": result.continuity_applied,
                "final_confidence": result.final_confidence,
                "confidence_label": result.confidence_label.value,
                "prediction_made": result.prediction_made,
                "xgb_error_minutes": xgb_error_minutes,
                "fused_error_minutes": fused_error_minutes,
            }
        )

    return pd.DataFrame(records)


def summarize_fusion_report(df: pd.DataFrame) -> dict:
    """The 8 required summary statistics, plus a couple of supporting ones."""

    disagreement = df["disagreement_minutes"].dropna()
    xgb_errors = df["xgb_error_minutes"].dropna()
    fused_errors = df["fused_error_minutes"].dropna()

    return {
        "n_windows": len(df),
        "disagreement_minutes_summary": disagreement.describe().to_dict() if len(disagreement) else {},
        "disagreement_regime_counts": df["disagreement_regime"].value_counts(dropna=False).to_dict(),
        "mean_xgb_final_weight": float(df["xgb_final_weight"].mean()),
        "mean_state_final_weight": float(df["state_final_weight"].mean()),
        "n_continuity_caps_applied": int(df["continuity_applied"].sum()),
        "final_confidence_summary": df["final_confidence"].describe().to_dict(),
        "confidence_label_counts": df["confidence_label"].value_counts(dropna=False).to_dict(),
        "prediction_made_counts": df["prediction_made"].value_counts(dropna=False).to_dict(),
        "xgb_mae_minutes": float(xgb_errors.mean()) if len(xgb_errors) else None,
        "fused_mae_minutes": float(fused_errors.mean()) if len(fused_errors) else None,
        "mae_improvement_minutes": (
            float(xgb_errors.mean() - fused_errors.mean()) if len(xgb_errors) and len(fused_errors) else None
        ),
    }


def build_diagnostics_plots(df: pd.DataFrame, output_dir: Path) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written = {}

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(df["disagreement_minutes"].dropna(), bins=40, color="tab:blue")
    ax.set_xlabel("XGB vs. state disagreement (minutes)")
    ax.set_ylabel("Count")
    ax.set_title("Disagreement distribution")
    fig.tight_layout()
    path = output_dir / "01_disagreement_distribution.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["disagreement_distribution"] = path

    fig, ax = plt.subplots(figsize=(7, 5))
    order = ["normal", "moderate", "large", "extreme"]
    counts = df["disagreement_regime"].value_counts()
    ax.bar(order, [counts.get(r, 0) for r in order], color="tab:orange")
    ax.set_xlabel("Disagreement regime")
    ax.set_ylabel("Count")
    ax.set_title("Disagreement regime frequencies")
    fig.tight_layout()
    path = output_dir / "02_regime_frequencies.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["regime_frequencies"] = path

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(df["final_confidence"], bins=30, color="tab:green")
    ax.set_xlabel("Final confidence score")
    ax.set_ylabel("Count")
    ax.set_title("Confidence distribution")
    fig.tight_layout()
    path = output_dir / "03_confidence_distribution.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["confidence_distribution"] = path

    fig, ax = plt.subplots(figsize=(7, 5))
    xgb_mae = df["xgb_error_minutes"].dropna().mean()
    fused_mae = df["fused_error_minutes"].dropna().mean()
    ax.bar(["XGBoost alone", "Fused"], [xgb_mae, fused_mae], color=["tab:red", "tab:purple"])
    ax.set_ylabel("MAE vs. synthetic ground truth (minutes)")
    ax.set_title("XGBoost error vs. fused error (see caveat in docs/dlmo_fusion.md)")
    fig.tight_layout()
    path = output_dir / "04_xgb_vs_fused_error.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["xgb_vs_fused_error"] = path

    return written
