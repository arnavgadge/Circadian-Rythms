"""The alignment diagnostic experiment: run the engine over a synthetic
population and summarize the resulting distributions.

**Synthetic-data warning** (repeated here because it materially affects
how to read this report): the synthetic data generator itself creates
the behavioral patterns and DLMO relationships these scores are
computed from, so alignment-score distributions partly reflect the
simulator's own assumptions. The correct reading is "under the current
synthetic data-generating configuration, the alignment distribution
is..." -- never "X% of humans are aligned." See
``docs/alignment_engine.md`` "Limitations".
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from app.alignment.config import DEFAULT_ALIGNMENT_CONFIG, AlignmentConfig
from app.alignment.engine import compute_alignment
from app.alignment.inputs import AlignmentInputs


def run_alignment_over_rows(rows: list, config: AlignmentConfig = DEFAULT_ALIGNMENT_CONFIG) -> pd.DataFrame:
    """``rows`` is a list of dicts, each with an ``AlignmentInputs``
    under ``"inputs"`` plus arbitrary passthrough metadata (participant
    id, chronotype, personality, date, ...). Returns one summary row
    per input.
    """

    records = []
    for row in rows:
        inputs: AlignmentInputs = row["inputs"]
        result = compute_alignment(inputs, config)
        record = {k: v for k, v in row.items() if k != "inputs"}
        record.update(
            {
                "final_score": result.final_score,
                "phase_score": result.phase_score,
                "behavioral_score": result.behavioral_score,
                "phase_difference_minutes": result.phase_difference_minutes,
                "data_completeness": result.data_completeness,
                "n_imputed_components": len(result.imputed_components),
            }
        )
        for name, component in result.behavioral_components.items():
            record[f"component_{name}_score"] = component.score
        records.append(record)

    return pd.DataFrame(records)


def summarize_alignment_report(df: pd.DataFrame) -> dict:
    component_cols = [c for c in df.columns if c.startswith("component_")]
    return {
        "n_rows": len(df),
        "final_score_summary": df["final_score"].describe().to_dict(),
        "phase_score_summary": df["phase_score"].describe().to_dict(),
        "behavioral_score_summary": df["behavioral_score"].describe().to_dict(),
        "component_score_summaries": {c: df[c].describe().to_dict() for c in component_cols},
        "mean_data_completeness": float(df["data_completeness"].mean()),
        "rows_with_imputation": int((df["n_imputed_components"] > 0).sum()),
    }


def build_diagnostics_plots(df: pd.DataFrame, output_dir: Path) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written = {}

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    for ax, col, title in zip(
        axes, ["final_score", "phase_score", "behavioral_score"], ["Final alignment", "Phase alignment", "Behavioral alignment"]
    ):
        ax.hist(df[col], bins=30, color="tab:blue")
        ax.set_title(title)
        ax.set_xlabel("Score (0-100)")
    fig.suptitle("Alignment score distributions (synthetic data -- see docs/alignment_engine.md)")
    fig.tight_layout()
    path = output_dir / "01_score_distributions.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["score_distributions"] = path

    component_cols = [c for c in df.columns if c.startswith("component_")]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.boxplot([df[c].dropna() for c in component_cols], tick_labels=[c.replace("component_", "").replace("_score", "") for c in component_cols], showmeans=True)
    ax.set_ylabel("Score (0-100)")
    ax.set_title("Behavioral component score distributions")
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    path = output_dir / "02_component_distributions.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["component_distributions"] = path

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(df["phase_difference_minutes"].abs(), df["phase_score"], s=6, alpha=0.3)
    ax.set_xlabel("|phase deviation| (minutes)")
    ax.set_ylabel("Phase score")
    ax.set_title("Phase deviation vs. phase score")
    fig.tight_layout()
    path = output_dir / "03_deviation_vs_score.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["deviation_vs_score"] = path

    if "chronotype" in df.columns:
        fig, ax = plt.subplots(figsize=(7, 5))
        order = [c for c in ["Early", "Intermediate", "Late"] if c in df["chronotype"].unique()]
        ax.boxplot([df.loc[df["chronotype"] == c, "final_score"] for c in order], tick_labels=order, showmeans=True)
        ax.set_ylabel("Final alignment score")
        ax.set_title("Alignment by chronotype")
        fig.tight_layout()
        path = output_dir / "04_alignment_by_chronotype.png"
        fig.savefig(path, dpi=120)
        plt.close(fig)
        written["alignment_by_chronotype"] = path

    if "personality_key" in df.columns:
        fig, ax = plt.subplots(figsize=(10, 5))
        order = sorted(df["personality_key"].dropna().unique())
        ax.boxplot([df.loc[df["personality_key"] == p, "final_score"] for p in order], tick_labels=order, showmeans=True)
        ax.set_ylabel("Final alignment score")
        ax.set_title("Alignment by behavioral personality")
        ax.tick_params(axis="x", rotation=25)
        fig.tight_layout()
        path = output_dir / "05_alignment_by_personality.png"
        fig.savefig(path, dpi=120)
        plt.close(fig)
        written["alignment_by_personality"] = path

    return written
