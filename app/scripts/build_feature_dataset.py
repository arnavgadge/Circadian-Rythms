"""CLI for the CircadianIQ Version-1 feature-engineering layer.

Run with:

    python -m app.scripts.build_feature_dataset
    python -m app.scripts.build_feature_dataset --output-dir data/processed

Reads directly from the database populated by Phase 3 (``python -m
app.scripts.generate_synthetic_data``) and writes the resulting
feature matrix, metadata, and target references as Parquet -- derived
artifacts for the Phase 5 training pipeline, not an authoritative
store (SQL remains that).
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
from app.features.dataset import build_feature_dataset_for_all_participants
from app.features.diagnostics import build_diagnostics_report
from app.logging_config import setup_logging


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(PROJECT_ROOT / "data" / "processed"),
        help="Directory for the Parquet feature matrix/metadata/targets and diagnostics.",
    )
    parser.add_argument("--no-diagnostics", action="store_true", default=False)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    app_config = load_config()
    setup_logging(app_config.log_level)

    engine = create_app_engine(app_config)
    session_factory = create_session_factory(engine)
    session = session_factory()

    print("Building feature dataset for every participant in the database...")
    dataset = build_feature_dataset_for_all_participants(session)
    session.close()

    print(f"X shape: {dataset.X.shape} (rows x features)")
    print(f"metadata rows: {len(dataset.metadata)}")
    print(f"targets rows: {len(dataset.targets)}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset.X.to_parquet(output_dir / "feature_matrix.parquet", index=False)
    dataset.metadata.to_parquet(output_dir / "feature_metadata.parquet", index=False)
    dataset.targets.to_parquet(output_dir / "feature_targets.parquet", index=False)
    print(f"Exported feature matrix/metadata/targets to: {output_dir}")

    if not args.no_diagnostics:
        written = build_diagnostics_report(dataset, output_dir / "diagnostics")
        print(f"Diagnostics written to: {output_dir / 'diagnostics'}")
        for name, path in written.items():
            print(f"  {name}: {path}")

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
