"""The recommendation-engine diagnostic experiment: run the engine over
a synthetic population and summarize the resulting distributions.

**Synthetic-data warning**: these distributions are properties of the
Phase 3 synthetic generator's own construction (and of this phase's
own catalogue placeholder assumptions), not evidence about real human
behavior or intervention effectiveness -- see
``docs/recommendation_engine.md`` "Synthetic-data interpretation".
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from app.recommendations.engine import RecommendationResult, select_recommendations
from app.recommendations.inputs import RecommendationInputs


def run_recommendations_over_rows(rows: list) -> pd.DataFrame:
    """``rows``: list of dicts, each with a ``RecommendationInputs`` under
    ``"inputs"`` plus passthrough metadata."""

    records = []
    for row in rows:
        inputs: RecommendationInputs = row["inputs"]
        result: RecommendationResult = select_recommendations(inputs)
        meta = {k: v for k, v in row.items() if k != "inputs"}

        selections = [result.primary] + list(result.supporting) if result.primary else list(result.supporting)
        for selection in selections:
            record = dict(meta)
            record.update(
                {
                    "intervention_code": selection.intervention_code,
                    "priority": selection.priority,
                    "is_primary": selection.priority == 1,
                    "severity": result.severity,
                    "contributor_signal": selection.contributor_signal,
                    "candidate_score": selection.candidate_score,
                    "feasibility_score": selection.feasibility_score,
                    "impact_score": selection.impact_score,
                    "expected_improvement_minutes": selection.expected_improvement_minutes,
                    "target_gap": abs(selection.graduated_target.raw_gap),
                }
            )
            records.append(record)

    return pd.DataFrame(records)


def summarize_recommendation_report(df: pd.DataFrame) -> dict:
    primary = df[df["is_primary"]]
    return {
        "n_participant_days": df.groupby([c for c in ("participant_id", "target_date") if c in df.columns]).ngroups
        if {"participant_id", "target_date"}.issubset(df.columns)
        else None,
        "primary_frequency_by_intervention": primary["intervention_code"].value_counts().to_dict(),
        "supporting_frequency_by_intervention": df[df["priority"] != 1]["intervention_code"].value_counts().to_dict(),
        "severity_distribution": df.drop_duplicates(
            [c for c in ("participant_id", "target_date") if c in df.columns]
        )["severity"].value_counts().to_dict()
        if {"participant_id", "target_date"}.issubset(df.columns)
        else df["severity"].value_counts().to_dict(),
        "average_graduated_target_gap": float(df["target_gap"].mean()),
        "average_feasibility": float(df["feasibility_score"].mean()),
        "average_expected_improvement_minutes": float(df["expected_improvement_minutes"].dropna().mean())
        if df["expected_improvement_minutes"].notna().any()
        else None,
        "primary_by_personality": (
            {
                f"{personality}/{intervention}": count
                for (personality, intervention), count in primary.groupby("personality_key")[
                    "intervention_code"
                ].value_counts().items()
            }
            if "personality_key" in primary.columns
            else None
        ),
        "primary_by_chronotype": (
            {
                f"{chronotype}/{intervention}": count
                for (chronotype, intervention), count in primary.groupby("chronotype")[
                    "intervention_code"
                ].value_counts().items()
            }
            if "chronotype" in primary.columns
            else None
        ),
    }


def build_diagnostics_plots(df: pd.DataFrame, output_dir: Path) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written = {}

    primary = df[df["is_primary"]]

    fig, ax = plt.subplots(figsize=(8, 5))
    counts = primary["intervention_code"].value_counts()
    ax.bar(counts.index, counts.values, color="tab:blue")
    ax.set_title("Primary intervention frequency")
    ax.set_ylabel("Count")
    ax.tick_params(axis="x", rotation=25)
    fig.tight_layout()
    path = output_dir / "01_primary_frequency.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["primary_frequency"] = path

    fig, ax = plt.subplots(figsize=(7, 5))
    severity_order = ["good", "mild", "moderate", "severe"]
    severity_counts = primary["severity"].value_counts().reindex(severity_order).fillna(0)
    ax.bar(severity_counts.index, severity_counts.values, color="tab:orange")
    ax.set_title("Severity distribution (primary selections)")
    ax.set_ylabel("Count")
    fig.tight_layout()
    path = output_dir / "02_severity_distribution.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["severity_distribution"] = path

    if "personality_key" in primary.columns:
        fig, ax = plt.subplots(figsize=(10, 5))
        order = sorted(primary["personality_key"].dropna().unique())
        counts_by_personality = pd.crosstab(primary["personality_key"], primary["intervention_code"])
        counts_by_personality.reindex(order).plot(kind="bar", stacked=True, ax=ax)
        ax.set_title("Primary intervention by behavioral personality")
        ax.set_ylabel("Count")
        ax.tick_params(axis="x", rotation=25)
        fig.tight_layout()
        path = output_dir / "03_primary_by_personality.png"
        fig.savefig(path, dpi=120)
        plt.close(fig)
        written["primary_by_personality"] = path

    return written
