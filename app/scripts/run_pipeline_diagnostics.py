"""CLI for the Phase 11 daily-inference-pipeline diagnostic experiment.

Run with:

    python -m app.scripts.run_pipeline_diagnostics [--participants N]

Builds a fresh, isolated SQLite database, generates a Phase 3
synthetic population into it, seeds the Phase 10 intervention
catalogue, then runs ``run_daily_inference`` for every participant at
two target days (the first day sufficient history exists, and a later
day) -- reporting the batch diagnostics required by the Phase 11 brief.

**No parameter is tuned from this run** -- see
``app.pipeline.diagnostics`` module docstring.
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

from app.config.settings import AppConfig
from app.database.engine import create_app_engine, create_session_factory
from app.database.init_db import create_all_tables
from app.database.models import Participant
from app.database.seed import seed_reference_data
from app.logging_config import setup_logging
from app.pipeline.config import DEFAULT_PIPELINE_CONFIG
from app.pipeline.diagnostics import report_dict, summarize_batch
from app.pipeline.orchestrator import run_daily_inference
from app.synthetic.config import DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC, SimulationRunConfig
from app.synthetic.db_writer import write_dataset_to_db
from app.synthetic.simulator import generate_synthetic_dataset


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--participants", type=int, default=50)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument(
        "--db-path", type=str, default=str(PROJECT_ROOT / "data" / "processed" / "pipeline_diagnostics.db")
    )
    parser.add_argument(
        "--output-dir", type=str, default=str(PROJECT_ROOT / "data" / "processed" / "pipeline_diagnostics")
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    setup_logging("INFO")

    db_path = Path(args.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    config = AppConfig(
        environment="diagnostics",
        database_url=f"sqlite:///{db_path}",
        data_dir=PROJECT_ROOT / "data",
        raw_data_dir=PROJECT_ROOT / "data" / "raw",
        synthetic_data_dir=PROJECT_ROOT / "data" / "synthetic",
        processed_data_dir=PROJECT_ROOT / "data" / "processed",
        model_dir=PROJECT_ROOT / "models",
        log_level="INFO",
    )

    print(f"Building a fresh diagnostics database at {db_path} ...")
    engine = create_app_engine(config)
    create_all_tables(engine)
    session_factory = create_session_factory(engine)

    print(f"Generating synthetic dataset ({args.participants} participants x {args.days} days, seed 42)...")
    run_cfg = SimulationRunConfig(num_participants=args.participants, num_days=args.days, seed=42)
    dataset = generate_synthetic_dataset(run_cfg, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)
    write_dataset_to_db(dataset, session_factory)

    session = session_factory()
    seed_reference_data(session)
    participant_ids = list(session.execute(select(Participant.id).order_by(Participant.id)).scalars().all())
    session.close()

    print(f"Running daily inference for {len(participant_ids)} participants at two target days each...")
    results = []
    for pid in participant_ids:
        session = session_factory()
        try:
            from app.database.models import DailyObservation

            dates = list(
                session.execute(
                    select(DailyObservation.observation_date)
                    .where(DailyObservation.participant_id == pid)
                    .order_by(DailyObservation.observation_date)
                ).scalars().all()
            )
        finally:
            session.close()

        if len(dates) < DEFAULT_PIPELINE_CONFIG.min_consecutive_history_days + 4:
            continue

        target_dates = [dates[DEFAULT_PIPELINE_CONFIG.min_consecutive_history_days], dates[-1]]
        for target_date in target_dates:
            result = run_daily_inference(pid, target_date, session_factory, force_rerun=True)
            results.append(result)

    diag = summarize_batch(results)
    summary = report_dict(diag)

    print("\n=== Pipeline diagnostic summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "pipeline_diagnostics_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\nSummary written to: {output_dir / 'pipeline_diagnostics_summary.json'}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
