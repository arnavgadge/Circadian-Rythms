"""CLI for the Phase 8 alignment diagnostic experiment.

Run with:

    python -m app.scripts.run_alignment_diagnostics [--participants N]

Runs the alignment engine over a sample of participants' six-day
windows from the synthetic database, using the stored
``circadian_labels.fused_dlmo_time`` (Phase 3's ground-truth
trajectory) directly as the fused DLMO input -- a reasonable
simplification for this diagnostic (Phase 8 only needs *a* fused DLMO
value to score against; it does not need to re-run the full Phase
5+6+7 pipeline for every window).

**Synthetic-data warning**: see ``app.alignment.diagnostics`` and
``docs/alignment_engine.md`` -- these distributions characterize the
synthetic data-generating system, not human circadian alignment.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from app.alignment.db_adapter import build_alignment_inputs
from app.alignment.diagnostics import build_diagnostics_plots, run_alignment_over_rows, summarize_alignment_report
from app.config.settings import load_config
from app.database.engine import create_app_engine, create_session_factory
from app.database.models import CircadianLabel, DailyObservation, Participant, ParticipantProfile
from app.features.windows import compute_valid_windows
from app.logging_config import setup_logging


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--participants", type=int, default=200, help="Number of participants to sample.")
    parser.add_argument("--windows-per-participant", type=int, default=4, help="Windows sampled per participant.")
    parser.add_argument("--output-dir", type=str, default=str(PROJECT_ROOT / "data" / "processed" / "alignment_diagnostics"))
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    app_config = load_config()
    setup_logging(app_config.log_level)

    engine = create_app_engine(app_config)
    session = create_session_factory(engine)()

    participant_ids = list(
        session.execute(select(Participant.id).order_by(Participant.id).limit(args.participants)).scalars().all()
    )
    print(f"Sampling {len(participant_ids)} participants...")

    rows = []
    for participant_id in participant_ids:
        profile = session.get(ParticipantProfile, participant_id)
        personality = (profile.synthetic_personality_profile or {}).get("personality") if profile else None

        observations = {
            o.observation_date: o
            for o in session.execute(
                select(DailyObservation)
                .where(DailyObservation.participant_id == participant_id)
                .order_by(DailyObservation.observation_date)
            ).scalars().all()
        }
        dates = list(observations.keys())
        windows = compute_valid_windows(participant_id, dates, window_size_days=6)
        sampled_windows = windows[:: max(1, len(windows) // args.windows_per_participant)][: args.windows_per_participant]

        for window in sampled_windows:
            label = session.execute(
                select(CircadianLabel).where(
                    CircadianLabel.participant_id == participant_id,
                    CircadianLabel.target_date == window.target_date,
                    CircadianLabel.is_latest.is_(True),
                )
            ).scalars().first()
            if label is None or label.fused_dlmo_time is None:
                continue

            from app.synthetic.time_utils import clock_time_to_hour

            window_obs = [observations[d] for d in window.day_dates if d in observations]
            if len(window_obs) < 6:
                continue

            inputs = build_alignment_inputs(
                fused_dlmo_hour=clock_time_to_hour(label.fused_dlmo_time),
                window_observations=window_obs,
                chronotype=profile.chronotype_category if profile else None,
            )
            rows.append(
                {
                    "inputs": inputs,
                    "participant_id": participant_id,
                    "target_date": window.target_date,
                    "chronotype": profile.chronotype_category if profile else None,
                    "personality_key": personality,
                }
            )

    session.close()
    print(f"Computing alignment for {len(rows)} participant-windows...")

    df = run_alignment_over_rows(rows)
    summary = summarize_alignment_report(df)

    print("\n=== Alignment diagnostic summary ===")
    print(f"rows: {summary['n_rows']}")
    print(f"final score: mean={summary['final_score_summary']['mean']:.1f}, std={summary['final_score_summary']['std']:.1f}")
    print(f"phase score: mean={summary['phase_score_summary']['mean']:.1f}")
    print(f"behavioral score: mean={summary['behavioral_score_summary']['mean']:.1f}")
    print(f"mean data completeness: {summary['mean_data_completeness']:.3f}")
    print(f"rows with imputation: {summary['rows_with_imputation']}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_dir / "alignment_results.parquet", index=False)
    (output_dir / "alignment_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    written = build_diagnostics_plots(df, output_dir / "plots")
    print(f"\nPlots written to: {output_dir / 'plots'}")
    for name, path in written.items():
        print(f"  {name}: {path}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
