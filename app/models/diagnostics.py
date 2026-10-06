"""Diagnostic plots for the trained DLMO model.

Research diagnostics only -- not application UI. Every plot involving
a clock-time axis either uses the 24-hour circular representation
directly or explicitly unwraps around midnight; a bare linear-hour
scatter/histogram is never used alone for a quantity that wraps.
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from app.models.training import TrainingResult
from app.synthetic.time_utils import circular_diff_hours


def _circular_errors(df: pd.DataFrame) -> np.ndarray:
    return np.array(
        [
            circular_diff_hours(a, p) * 60.0
            for a, p in zip(df["actual_dlmo_hour"], df["predicted_dlmo_hour"])
        ]
    )


def build_diagnostics_plots(result: TrainingResult, output_dir: Path) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written = {}

    df = result.test_predictions.copy()
    df["error_minutes"] = _circular_errors(df)

    # 1. Actual vs predicted DLMO on a circular clock representation.
    fig = plt.figure(figsize=(7, 7))
    ax = fig.add_subplot(111, projection="polar")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    actual_theta = df["actual_dlmo_hour"] / 24.0 * 2 * math.pi
    predicted_theta = df["predicted_dlmo_hour"] / 24.0 * 2 * math.pi
    ax.scatter(actual_theta, [1.0] * len(df), s=6, alpha=0.4, label="Actual", color="tab:blue")
    ax.scatter(predicted_theta, [0.9] * len(df), s=6, alpha=0.4, label="Predicted", color="tab:orange")
    ax.set_xticks(np.linspace(0, 2 * math.pi, 24, endpoint=False))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(24)], fontsize=6)
    ax.set_yticklabels([])
    ax.set_title("Actual vs. predicted DLMO (circular clock)")
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=8)
    fig.tight_layout()
    path = output_dir / "01_actual_vs_predicted_circular.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["actual_vs_predicted_circular"] = path

    # 2. Absolute error distribution.
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(df["error_minutes"].abs(), bins=40, color="tab:blue", alpha=0.8)
    ax.set_xlabel("Absolute circular error (minutes)")
    ax.set_ylabel("Count")
    ax.set_title("Absolute error distribution (held-out test set)")
    fig.tight_layout()
    path = output_dir / "02_absolute_error_distribution.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["absolute_error_distribution"] = path

    # 3. Signed error distribution.
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(df["error_minutes"], bins=40, color="tab:purple", alpha=0.8)
    ax.axvline(0, color="black", linewidth=1)
    ax.set_xlabel("Signed circular error, actual - predicted (minutes)")
    ax.set_ylabel("Count")
    ax.set_title("Signed error distribution (held-out test set)")
    fig.tight_layout()
    path = output_dir / "03_signed_error_distribution.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["signed_error_distribution"] = path

    # 4. Predicted vs actual DLMO (linear scatter, for a familiar view --
    # supplementary to plot 1, not a substitute for the circular one).
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(df["actual_dlmo_hour"], df["predicted_dlmo_hour"], s=6, alpha=0.3)
    ax.plot([0, 24], [0, 24], color="red", linewidth=1, linestyle="--")
    ax.set_xlabel("Actual DLMO (hour)")
    ax.set_ylabel("Predicted DLMO (hour)")
    ax.set_title("Predicted vs. actual DLMO (linear hour view)")
    fig.tight_layout()
    path = output_dir / "04_predicted_vs_actual_scatter.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["predicted_vs_actual_scatter"] = path

    # 5. Performance by chronotype.
    path = output_dir / "05_performance_by_chronotype.png"
    _bar_metric_by_group(result.chronotype_metrics, "mae_minutes", "Chronotype", "MAE (minutes)", "Performance by chronotype", path)
    written["performance_by_chronotype"] = path

    # 6. Performance by behavioral personality.
    path = output_dir / "06_performance_by_personality.png"
    _bar_metric_by_group(result.personality_metrics, "mae_minutes", "Personality", "MAE (minutes)", "Performance by behavioral personality", path, rotate=True)
    written["performance_by_personality"] = path

    # 7. Feature importance (top 20, gain-based).
    top_features = result.feature_importance_gain.head(20)
    fig, ax = plt.subplots(figsize=(9, 8))
    ax.barh(top_features["feature"][::-1], top_features["mean_importance"][::-1], color="tab:green")
    ax.set_xlabel("Mean gain importance (sin + cos models averaged)")
    ax.set_title("Top 20 features by gain-based importance")
    fig.tight_layout()
    path = output_dir / "07_feature_importance.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["feature_importance"] = path

    # 8. Residual/error by completeness band.
    path = output_dir / "08_error_by_completeness.png"
    _boxplot_error_by_group(df, "completeness_band", path)
    written["error_by_completeness"] = path

    return written


def _bar_metric_by_group(metrics_df: pd.DataFrame, metric_col: str, xlabel: str, ylabel: str, title: str, path: Path, rotate: bool = False) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(metrics_df["group"].astype(str), metrics_df[metric_col], color="tab:blue")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    if rotate:
        ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _boxplot_error_by_group(df: pd.DataFrame, group_col: str, path: Path) -> None:
    groups = sorted(df[group_col].dropna().unique())
    data = [df.loc[df[group_col] == g, "error_minutes"].abs().to_numpy() for g in groups]
    fig, ax = plt.subplots(figsize=(7, 5))
    if data and any(len(d) for d in data):
        ax.boxplot(data, tick_labels=[str(g) for g in groups], showmeans=True)
    ax.set_xlabel("Data-completeness band")
    ax.set_ylabel("Absolute circular error (minutes)")
    ax.set_title("Error by data-completeness band")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
