"""CLI for the CircadianIQ synthetic population + 30-day data generator.

Run with:

    python -m app.scripts.generate_synthetic_data
    python -m app.scripts.generate_synthetic_data --participants 1000 --days 30 --seed 42
    python -m app.scripts.generate_synthetic_data --reset

``--reset`` deletes every existing participant (and, via
``ON DELETE CASCADE``, everything that depends on one) before
generating fresh data. It is never the default -- you must pass it
explicitly.

Schema must already exist (run ``python scripts/init_db.py`` first);
this script only generates and writes data, it does not run
migrations.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import load_config
from app.database.engine import create_app_engine, create_session_factory
from app.logging_config import setup_logging
from app.synthetic.config import DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC, SimulationRunConfig
from app.synthetic.db_writer import reset_all_participants, write_dataset_to_db
from app.synthetic.diagnostics import build_diagnostics_report
from app.synthetic.export import export_dataset
from app.synthetic.simulator import generate_synthetic_dataset
from app.synthetic.validation import run_quality_checks


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--participants", type=int, default=1000, help="Number of participants to generate.")
    parser.add_argument("--days", type=int, default=30, help="Number of days per participant.")
    parser.add_argument("--seed", type=int, default=42, help="Master random seed (reproducibility).")
    parser.add_argument(
        "--reset",
        action="store_true",
        default=False,
        help="Delete all existing participants (and their data) before generating. NOT the default.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(PROJECT_ROOT / "data" / "synthetic"),
        help="Directory for Parquet/manifest export and diagnostics.",
    )
    parser.add_argument("--no-export", action="store_true", default=False, help="Skip Parquet/manifest export.")
    parser.add_argument(
        "--no-diagnostics", action="store_true", default=False, help="Skip the diagnostics report and plots."
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        default=False,
        help="Skip writing to the database (generate/validate/export only).",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    app_config = load_config()
    setup_logging(app_config.log_level)

    run_config = SimulationRunConfig(
        num_participants=args.participants,
        num_days=args.days,
        seed=args.seed,
    )

    print(
        f"Generating synthetic dataset: {run_config.num_participants} participants x "
        f"{run_config.num_days} days (seed={run_config.seed})..."
    )
    dataset = generate_synthetic_dataset(run_config, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)

    report = run_quality_checks(dataset, DEFAULT_SYNTHETIC)
    print("\nValidation:")
    for line in report.summary_lines():
        print(f"  {line}")
    report.raise_if_failed()

    output_dir = Path(args.output_dir)

    if not args.no_export:
        exported = export_dataset(dataset, output_dir)
        print(f"\nExported derived artifacts to: {output_dir}")
        for name, path in exported.items():
            print(f"  {name}: {path}")

    if not args.no_diagnostics:
        diagnostics_dir = output_dir / "diagnostics"
        written = build_diagnostics_report(dataset, diagnostics_dir)
        print(f"\nDiagnostics written to: {diagnostics_dir}")
        for name, path in written.items():
            print(f"  {name}: {path}")

    if not args.no_db:
        engine = create_app_engine(app_config)
        session_factory = create_session_factory(engine)

        if args.reset:
            print("\n--reset passed: deleting all existing participants...")
            deleted = reset_all_participants(session_factory)
            print(f"  deleted {deleted} participant row(s) (cascaded to their owned data).")

        print("\nWriting dataset to the database...")
        result = write_dataset_to_db(dataset, session_factory)
        print(
            f"  participants: {result.participants_written}, "
            f"daily_observations: {result.daily_observations_written}, "
            f"physiology_logs: {result.physiology_logs_written}, "
            f"circadian_labels: {result.circadian_labels_written}"
        )
    else:
        print("\n--no-db passed: skipped database write.")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
