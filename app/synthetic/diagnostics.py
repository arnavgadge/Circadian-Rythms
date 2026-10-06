"""Distribution diagnostics: a markdown summary plus PNG plots.

These are developer/QA diagnostic artifacts confirming the generator
actually produces the intended behavioral diversity -- not application
UI, and not part of the authoritative dataset. Everything here reads
from a :class:`~app.synthetic.simulator.SyntheticDataset` that has
already been generated; nothing here mutates it.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: never try to open a GUI window

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from app.synthetic.simulator import SyntheticDataset
from app.synthetic.time_utils import circular_diff_hours, circular_mean_hours, circular_std_hours

_PERSONALITY_ORDER = [
    "consistent_early_bird",
    "healthy_stable_routine",
    "late_eater",
    "screen_heavy_user",
    "social_jetlag_student",
    "consistent_night_owl",
    "chaotic_sleeper",
]


def _unwrap_hours(values: np.ndarray) -> np.ndarray:
    """Circularly unwrap a sequence of clock hours for smooth line plots.

    Without this, a trajectory crossing midnight (e.g. 23.9 -> 0.1)
    would show as a vertical drop to zero instead of a small step.
    """

    unwrapped = values.copy().astype(float)
    for i in range(1, len(unwrapped)):
        while unwrapped[i] - unwrapped[i - 1] > 12.0:
            unwrapped[i] -= 24.0
        while unwrapped[i] - unwrapped[i - 1] < -12.0:
            unwrapped[i] += 24.0
    return unwrapped


def _shift_late_night(hours: pd.Series, split_hour: float = 12.0) -> pd.Series:
    """Remap hours below ``split_hour`` to ``hour + 24`` for plotting values
    that cluster in the evening/night/early-morning band without the
    midnight-wraparound artifact splitting the distribution in two."""

    return hours.where(hours >= split_hour, hours + 24.0)


def _circular_hour_summary(hours: pd.Series) -> dict:
    """Summary statistics for a column of clock hours, computed correctly
    for a circular quantity: circular mean/std (via
    ``app.synthetic.time_utils``), plus min/median/max on the
    midnight-shifted representation for human-readable reporting.

    Plain ``pandas.Series.describe()`` is wrong here whenever a
    chronotype's values straddle midnight (e.g. "late" chronotype
    DLMO) -- a few wrapped values near 0 would otherwise drag a linear
    mean/std far from the true circular center and inflate the std
    dramatically. See the DLMO-by-chronotype plot for the same fix.
    """

    values = hours.dropna().to_numpy()
    if len(values) == 0:
        return {"count": 0, "circular_mean_hour": float("nan"), "circular_std_hours": float("nan"),
                "shifted_min": float("nan"), "shifted_median": float("nan"), "shifted_max": float("nan")}

    shifted = _shift_late_night(hours.dropna()).to_numpy()
    return {
        "count": len(values),
        "circular_mean_hour": circular_mean_hours(values),
        "circular_std_hours": circular_std_hours(values),
        "shifted_min": float(np.min(shifted)),
        "shifted_median": float(np.median(shifted)),
        "shifted_max": float(np.max(shifted)),
    }


def _boxplot_by_personality(df: pd.DataFrame, value_col: str, title: str, ylabel: str, path: Path) -> None:
    order = [p for p in _PERSONALITY_ORDER if p in df["personality_key"].unique()]
    data = [df.loc[df["personality_key"] == p, value_col].dropna().to_numpy() for p in order]

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.boxplot(data, tick_labels=order, showmeans=True)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def build_diagnostics_report(dataset: SyntheticDataset, output_dir: Path) -> dict:
    """Write a markdown summary and six PNG plots under ``output_dir``.

    Returns a dict of the file paths written.
    """

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    p_df = dataset.participants_df
    d_df = dataset.daily_df.merge(
        p_df[["index", "personality_key", "chronotype"]],
        left_on="participant_index",
        right_on="index",
        suffixes=("", "_p"),
    )

    written: dict = {}

    # --- Plot 1: DLMO trajectory examples ---
    fig, ax = plt.subplots(figsize=(9, 5))
    sample_indices = p_df["index"].sample(min(8, len(p_df)), random_state=0)
    for idx in sample_indices:
        participant_days = d_df[d_df["participant_index"] == idx].sort_values("day_index")
        hours = _unwrap_hours(participant_days["current_dlmo_hour"].to_numpy())
        ax.plot(participant_days["day_index"], hours, marker="o", markersize=2, label=f"P{idx}")
    ax.set_title("DLMO trajectory examples (current DLMO, unwrapped hours)")
    ax.set_xlabel("Day index")
    ax.set_ylabel("Current DLMO (hours, unwrapped)")
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    path = output_dir / "01_dlmo_trajectories.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["dlmo_trajectories"] = path

    # --- Plot 2: DLMO distribution by chronotype ---
    # DLMO clusters in the evening/night and can wrap past midnight (this is
    # expected for the "late" chronotype in particular), so plotting the raw
    # hour would show wrapped values as spurious near-zero outliers. Shift
    # for display exactly as done for last-meal time below.
    fig, ax = plt.subplots(figsize=(8, 5))
    order = ["early", "intermediate", "late"]
    shifted_intrinsic = _shift_late_night(p_df["intrinsic_dlmo_hour"])
    data = [shifted_intrinsic[p_df["chronotype"] == c].to_numpy() for c in order]
    ax.boxplot(data, tick_labels=order, showmeans=True)
    ax.set_title("Intrinsic DLMO by chronotype")
    ax.set_ylabel("Intrinsic DLMO (hour, >=24 means past midnight)")
    fig.tight_layout()
    path = output_dir / "02_dlmo_by_chronotype.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["dlmo_by_chronotype"] = path

    # --- Plot 3: Social jetlag by personality ---
    path = output_dir / "03_social_jetlag_by_personality.png"
    _boxplot_by_personality(
        d_df.dropna(subset=["social_jetlag_minutes"]),
        "social_jetlag_minutes",
        "Social jetlag by personality",
        "Social jetlag (minutes)",
        path,
    )
    written["social_jetlag_by_personality"] = path

    # --- Plot 4: Screen timing by personality ---
    path = output_dir / "04_evening_screen_by_personality.png"
    _boxplot_by_personality(
        d_df,
        "evening_screen_duration_hours",
        "Evening screen duration by personality",
        "Evening screen duration (hours)",
        path,
    )
    written["screen_by_personality"] = path

    # --- Plot 5: Morning light exposure by personality ---
    path = output_dir / "05_morning_light_by_personality.png"
    _boxplot_by_personality(
        d_df,
        "morning_light_duration_minutes",
        "Morning light duration by personality",
        "Morning light duration (minutes)",
        path,
    )
    written["morning_light_by_personality"] = path

    # --- Plot 6: Last meal time by personality ---
    d_df = d_df.assign(last_meal_hour_shifted=_shift_late_night(d_df["last_meal_hour"]))
    path = output_dir / "06_last_meal_by_personality.png"
    _boxplot_by_personality(
        d_df,
        "last_meal_hour_shifted",
        "Last meal time by personality",
        "Last meal time (hour, >=24 means past midnight)",
        path,
    )
    written["last_meal_by_personality"] = path

    # --- Markdown summary ---
    lines = [
        "# CircadianIQ Synthetic Data -- Distribution Diagnostics",
        "",
        f"Generated at: {dataset.generated_at.isoformat()}",
        f"Seed: {dataset.run_config.seed} | Participants: {dataset.run_config.num_participants} | "
        f"Days: {dataset.run_config.num_days}",
        "",
        "## Chronotype proportions",
        p_df["chronotype"].value_counts(normalize=True).round(3).to_string(),
        "",
        "## Personality proportions",
        p_df["personality_key"].value_counts(normalize=True).round(3).to_string(),
        "",
        "## Intrinsic DLMO distribution (hours) by chronotype",
        "(circular mean/std; min/median/max shown midnight-shifted, so >=24 means past midnight)",
        pd.DataFrame(
            {c: _circular_hour_summary(p_df.loc[p_df["chronotype"] == c, "intrinsic_dlmo_hour"]) for c in ["early", "intermediate", "late"]}
        ).T.round(2).to_string(),
        "",
        "## Final current DLMO distribution (hours, circular)",
        pd.Series(_circular_hour_summary(p_df["final_current_dlmo_hour"])).round(2).to_string(),
        "",
        "## DLMO change over 30 days (final current vs. initial current, circular difference, hours)",
        pd.Series(
            [
                circular_diff_hours(final, initial)
                for final, initial in zip(p_df["final_current_dlmo_hour"], p_df["initial_current_dlmo_hour"])
            ]
        ).describe().round(2).to_string(),
        "",
        "## Sleep duration distribution (hours)",
        d_df["sleep_duration_hours"].describe().round(2).to_string(),
        "",
        "## Evening screen duration distribution (hours) by personality",
        d_df.groupby("personality_key")["evening_screen_duration_hours"].mean().round(2).to_string(),
        "",
        "## Morning light duration distribution (minutes) by personality",
        d_df.groupby("personality_key")["morning_light_duration_minutes"].mean().round(1).to_string(),
        "",
        "## Last meal time distribution (mean hour, shifted so post-midnight > 24) by personality",
        d_df.groupby("personality_key")["last_meal_hour_shifted"].mean().round(2).to_string(),
        "",
        "## Exercise timing distribution (mean hour) by personality",
        d_df.groupby("personality_key")["exercise_hour"].mean().round(2).to_string(),
        "",
        "## Caffeine distribution (mean amount mg, mean hour) by personality",
        d_df.groupby("personality_key")[["caffeine_amount_mg", "caffeine_hour"]].mean().round(2).to_string(),
        "",
        "## Social jetlag distribution (minutes, free days only) by personality",
        d_df.dropna(subset=["social_jetlag_minutes"])
        .groupby("personality_key")["social_jetlag_minutes"]
        .describe()
        .round(2)
        .to_string(),
        "",
    ]
    report_path = output_dir / "diagnostics_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    written["report"] = report_path

    return written
