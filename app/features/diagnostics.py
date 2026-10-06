"""Statistical sanity diagnostics for a generated feature matrix.

Reports, per feature: missingness rate (from the dataset's own
metadata, not re-inferred), min/max/mean/std, and the number of unique
values -- and flags constant/near-constant features for review. Never
deletes or modifies anything; this is a report, not a filter.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.features.dataset import FeatureDataset

NEAR_CONSTANT_STD_THRESHOLD = 1e-6
NEAR_CONSTANT_UNIQUE_RATIO_THRESHOLD = 0.01  # fewer than 1% unique values


def summarize_feature_matrix(dataset: FeatureDataset) -> pd.DataFrame:
    """Per-feature statistics: count, missingness, min/max/mean/std, n-unique."""

    X = dataset.X
    n_rows = len(X)

    rows = []
    for name in dataset.feature_names:
        series = X[name]
        n_unique = series.nunique(dropna=True)
        rows.append(
            {
                "feature": name,
                "count": series.count(),
                "missing_rate_in_matrix": 1.0 - (series.count() / n_rows) if n_rows else float("nan"),
                "min": series.min(),
                "max": series.max(),
                "mean": series.mean(),
                "std": series.std(),
                "n_unique": n_unique,
                "unique_ratio": n_unique / n_rows if n_rows else float("nan"),
                "near_constant": bool(
                    (series.std(skipna=True) is not None)
                    and (pd.isna(series.std()) or series.std() < NEAR_CONSTANT_STD_THRESHOLD)
                ),
            }
        )

    return pd.DataFrame(rows)


def build_diagnostics_report(dataset: FeatureDataset, output_dir: Path) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stats = summarize_feature_matrix(dataset)
    stats_path = output_dir / "feature_statistics.csv"
    stats.to_csv(stats_path, index=False)

    near_constant = stats.loc[stats["near_constant"], "feature"].tolist()

    lines = [
        "# CircadianIQ Feature Matrix -- Statistical Diagnostics",
        "",
        f"Rows: {len(dataset.X)} | Features: {len(dataset.feature_names)}",
        "",
        "## Missingness (fraction of dataset rows where the feature came from "
        "the raw window, i.e. was NOT imputed)",
        dataset.metadata[
            ["tier_1_missing", "tier_2_missing", "tier_3_missing", "missing_feature_count"]
        ].describe().round(4).to_string(),
        "",
        "## Overall completeness",
        dataset.metadata["completeness"].describe().round(4).to_string(),
        "",
        "## Near-constant features (std < "
        f"{NEAR_CONSTANT_STD_THRESHOLD}) -- reported for review, NOT removed",
        ", ".join(near_constant) if near_constant else "(none)",
        "",
        "## Full per-feature statistics",
        f"see {stats_path.name}",
        "",
    ]
    report_path = output_dir / "feature_diagnostics_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")

    return {"statistics_csv": stats_path, "report": report_path, "near_constant_features": near_constant}
