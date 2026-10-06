"""CLI for the Phase 9 contributor-ranking diagnostic experiment.

Run with:

    python -m app.scripts.run_contributor_diagnostics [--participants N]

Regenerates the Phase 3 synthetic dataset in memory (seed 42, matching
the database) and runs the alignment engine (Phase 8) followed by the
contributor ranking engine (Phase 9) over a sample of participants'
six-day windows, using the dataset's own ``current_dlmo_hour``
trajectory directly as the fused DLMO input (the same simplification
used by the Phase 7/8 diagnostic scripts -- this phase only needs *a*
fused DLMO value, not a full re-run of Phase 5+6+7).

**Synthetic-data warning**: see ``app.contributors.diagnostics`` and
``docs/contributor_ranking.md`` -- these distributions characterize the
synthetic data-generating system, not human behavior.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.alignment.engine import compute_alignment
from app.alignment.inputs import AlignmentInputs
from app.contributors.diagnostics import build_diagnostics_plots, run_contributors_over_rows, summarize_contributor_report
from app.contributors.inputs import ContributorInputs
from app.logging_config import setup_logging
from app.state.circadian_state import ParticipantPhaseTraits
from app.synthetic.config import DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC, SimulationRunConfig
from app.synthetic.simulator import generate_synthetic_dataset
from app.config.settings import load_config


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--participants", type=int, default=200)
    parser.add_argument("--windows-per-participant", type=int, default=3)
    parser.add_argument("--output-dir", type=str, default=str(PROJECT_ROOT / "data" / "processed" / "contributor_diagnostics"))
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    app_config = load_config()
    setup_logging(app_config.log_level)

    print("Regenerating the Phase 3 synthetic dataset (seed 42)...")
    run_cfg = SimulationRunConfig(num_participants=args.participants, num_days=30, seed=42)
    dataset = generate_synthetic_dataset(run_cfg, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)

    rows = []
    for _, participant in dataset.participants_df.iterrows():
        traits = ParticipantPhaseTraits(
            intrinsic_dlmo_hour=participant["intrinsic_dlmo_hour"],
            baseline_sleep_onset_hour=participant["baseline_sleep_onset_hour"],
            light_sensitivity=participant["light_sensitivity"],
            screen_sensitivity=participant["screen_sensitivity"],
            meal_sensitivity=participant["meal_sensitivity"],
            chronotype=participant["chronotype"],
        )
        participant_days = dataset.daily_df[
            dataset.daily_df["participant_index"] == participant["index"]
        ].sort_values("day_index").reset_index(drop=True)

        n_days = len(participant_days)
        window_size = run_cfg.window_size_days
        candidate_starts = list(range(0, n_days - window_size))
        step = max(1, len(candidate_starts) // args.windows_per_participant)
        sampled_starts = candidate_starts[::step][: args.windows_per_participant]

        for start in sampled_starts:
            window = participant_days.iloc[start : start + window_size]
            target_row = participant_days.iloc[start + window_size]

            alignment_inputs = AlignmentInputs(
                fused_dlmo_hour=target_row["current_dlmo_hour"],
                most_recent_sleep_onset_hour=window.iloc[-1]["sleep_onset_hour"],
                window_sleep_onset_hours=window["sleep_onset_hour"].tolist(),
                window_morning_light_duration_minutes=window["morning_light_duration_minutes"].tolist(),
                window_evening_screen_duration_hours=window["evening_screen_duration_hours"].tolist(),
                window_last_meal_hours=window["last_meal_hour"].tolist(),
                window_social_jetlag_minutes=window["social_jetlag_minutes"].tolist(),
                chronotype=participant["chronotype"],
            )
            alignment_result = compute_alignment(alignment_inputs)

            contributor_inputs = ContributorInputs(
                traits=traits,
                alignment_result=alignment_result,
                window_morning_light_duration_minutes=window["morning_light_duration_minutes"].tolist(),
                window_evening_screen_duration_hours=window["evening_screen_duration_hours"].tolist(),
                window_last_meal_hours=window["last_meal_hour"].tolist(),
                window_exercise_hours=window["exercise_hour"].tolist(),
                window_social_jetlag_minutes=window["social_jetlag_minutes"].tolist(),
                latest_morning_light_duration_minutes=target_row["morning_light_duration_minutes"],
                latest_evening_screen_duration_hours=target_row["evening_screen_duration_hours"],
                latest_last_meal_hour=target_row["last_meal_hour"],
                latest_exercise_hour=target_row["exercise_hour"],
                latest_social_jetlag_minutes=target_row["social_jetlag_minutes"],
            )

            rows.append(
                {
                    "inputs": contributor_inputs,
                    "participant_id": int(participant["index"]),
                    "target_date": target_row["date"],
                    "chronotype": participant["chronotype"],
                    "personality_key": participant["personality_key"],
                }
            )

    print(f"Ranking contributors for {len(rows)} participant-windows...")
    df = run_contributors_over_rows(rows)
    summary = summarize_contributor_report(df)

    print("\n=== Contributor diagnostic summary ===")
    print(f"top-1 frequency by signal: {summary['top1_frequency_by_signal']}")
    print(f"mean contributor score by signal: { {k: round(v, 1) for k, v in summary['mean_contributor_score_by_signal'].items()} }")
    print(f"anomaly frequency (any signal): {summary['anomaly_frequency_overall']:.3f}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_dir / "contributor_results.parquet", index=False)
    (output_dir / "contributor_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    written = build_diagnostics_plots(df, output_dir / "plots")
    print(f"\nPlots written to: {output_dir / 'plots'}")
    for name, path in written.items():
        print(f"  {name}: {path}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
