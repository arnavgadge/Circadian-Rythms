"""The contributor-ranking diagnostic experiment: run the engine over a
synthetic population and summarize the resulting distributions.

**Synthetic-data warning**: these distributions are properties of the
Phase 3 synthetic generator's own construction, not evidence about
real human behavior -- see ``docs/contributor_ranking.md``
"Synthetic-data interpretation warning".
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from app.contributors.engine import ContributorResult, rank_contributors
from app.contributors.inputs import ContributorInputs


def run_contributors_over_rows(rows: list) -> pd.DataFrame:
    """``rows``: list of dicts, each with a ``ContributorInputs`` under
    ``"inputs"`` plus passthrough metadata (participant id, chronotype,
    personality, ...). Returns one row per (participant, rank<=3) plus
    one row per candidate signal for the full-distribution columns.
    """

    records = []
    for row in rows:
        inputs: ContributorInputs = row["inputs"]
        result: ContributorResult = rank_contributors(inputs)
        meta = {k: v for k, v in row.items() if k != "inputs"}

        top_signals = [c.signal for c in result.contributors]
        any_anomaly = any(v.is_anomaly for v in result.anomaly_details.values() if v.available)

        for candidate in result.all_candidates:
            record = dict(meta)
            record.update(
                {
                    "signal": candidate.signal,
                    "rank": candidate.rank,
                    "is_top_3": candidate.signal in top_signals,
                    "contributor_score": candidate.contributor_score,
                    "signed_phase_effect_minutes": candidate.signed_phase_effect_minutes,
                    "alignment_deficit": candidate.alignment_deficit,
                    "direction": candidate.direction,
                    "today_anomaly": candidate.today_anomaly,
                    "any_anomaly_today": any_anomaly,
                }
            )
            records.append(record)

    return pd.DataFrame(records)


def summarize_contributor_report(df: pd.DataFrame) -> dict:
    top3 = df[df["is_top_3"]]
    return {
        "n_participant_windows": df.groupby([c for c in ("participant_id", "target_date") if c in df.columns]).ngroups
        if {"participant_id", "target_date"}.issubset(df.columns)
        else None,
        "contributor_frequency_by_rank": {
            f"rank_{rank}/{signal}": count
            for (rank, signal), count in top3.groupby("rank")["signal"].value_counts().items()
        },
        "mean_contributor_score_by_signal": df.groupby("signal")["contributor_score"].mean().to_dict(),
        "mean_phase_effect_by_signal": df.groupby("signal")["signed_phase_effect_minutes"].mean().to_dict(),
        "mean_alignment_deficit_by_signal": df.groupby("signal")["alignment_deficit"].mean().to_dict(),
        "direction_counts_by_signal": {
            f"{signal}/{direction}": count
            for (signal, direction), count in df.groupby("signal")["direction"].value_counts().items()
        },
        "top1_frequency_by_signal": df[df["rank"] == 1]["signal"].value_counts().to_dict(),
        "anomaly_frequency_overall": float(df["any_anomaly_today"].mean()) if "any_anomaly_today" in df else None,
    }


def build_diagnostics_plots(df: pd.DataFrame, output_dir: Path) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written = {}

    top1 = df[df["rank"] == 1]
    fig, ax = plt.subplots(figsize=(8, 5))
    counts = top1["signal"].value_counts()
    ax.bar(counts.index, counts.values, color="tab:blue")
    ax.set_title("Top-1 contributor frequency by signal")
    ax.set_ylabel("Count")
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    path = output_dir / "01_top1_frequency.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["top1_frequency"] = path

    fig, ax = plt.subplots(figsize=(9, 5))
    signals = sorted(df["signal"].unique())
    ax.boxplot([df.loc[df["signal"] == s, "contributor_score"].dropna() for s in signals], tick_labels=signals, showmeans=True)
    ax.set_title("Contributor score distribution by signal")
    ax.set_ylabel("Contributor score")
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    path = output_dir / "02_score_distribution_by_signal.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["score_distribution_by_signal"] = path

    if "personality_key" in df.columns:
        fig, ax = plt.subplots(figsize=(10, 5))
        order = sorted(top1["personality_key"].dropna().unique())
        counts_by_personality = pd.crosstab(top1["personality_key"], top1["signal"])
        counts_by_personality.reindex(order).plot(kind="bar", stacked=True, ax=ax)
        ax.set_title("Top-1 contributor by behavioral personality")
        ax.set_ylabel("Count")
        ax.tick_params(axis="x", rotation=25)
        fig.tight_layout()
        path = output_dir / "03_top1_by_personality.png"
        fig.savefig(path, dpi=120)
        plt.close(fig)
        written["top1_by_personality"] = path

    return written
