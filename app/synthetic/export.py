"""Derived-artifact export (Parquet/CSV) and the generation manifest.

SQL is the authoritative store for the generated dataset (see
:mod:`app.synthetic.db_writer`); everything written here is a
convenience copy for inspection and for the Phase 4 feature-engineering
workflow, which needs the sliding-window metadata this phase produces
but that has no natural home as a new Phase 2 table (it is fully
re-derivable from ``daily_observations``/``circadian_labels`` by date
arithmetic -- see ``docs/synthetic_data_generation.md`` section 9 for
why it is kept out of the relational schema rather than added to it).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from app.synthetic.config import SimulationRunConfig
from app.synthetic.simulator import SyntheticDataset


def export_dataset(dataset: SyntheticDataset, output_dir: Path) -> dict:
    """Write participants/daily/windows tables as Parquet, plus a JSON
    generation manifest recording seed/config/version/timestamp.

    Returns a dict of the file paths written.
    """

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    participants_path = output_dir / "synthetic_participants.parquet"
    daily_path = output_dir / "synthetic_daily_observations.parquet"
    windows_path = output_dir / "synthetic_windows.parquet"

    dataset.participants_df.to_parquet(participants_path, index=False)
    dataset.daily_df.to_parquet(daily_path, index=False)
    dataset.windows_df.to_parquet(windows_path, index=False)

    manifest = build_manifest(dataset)
    manifest_path = output_dir / "generation_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    return {
        "participants": participants_path,
        "daily_observations": daily_path,
        "windows": windows_path,
        "manifest": manifest_path,
    }


def build_manifest(dataset: SyntheticDataset) -> dict:
    """Reproducibility metadata for one generation run.

    Records exactly the fields the project brief requires: seed,
    participant count, day count, generator version, configuration
    version, and timestamp.
    """

    run_config: SimulationRunConfig = dataset.run_config
    return {
        "seed": run_config.seed,
        "num_participants": run_config.num_participants,
        "num_days": run_config.num_days,
        "window_size_days": run_config.window_size_days,
        "generator_version": run_config.generator_version,
        "config_version": run_config.config_version,
        "start_date": run_config.start_date_iso,
        "generated_at": dataset.generated_at.isoformat(),
        "row_counts": {
            "participants": len(dataset.participants_df),
            "daily_observations": len(dataset.daily_df),
            "windows": len(dataset.windows_df),
        },
    }
