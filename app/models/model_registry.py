"""Versioned model artifact storage.

Never overwrites a previous version: :func:`next_version` scans the
models directory for existing ``xgboost_dlmo_sin_v*.pkl`` files and
returns one past the highest version found, so re-running training
always produces a new, distinct artifact set (and a new
``model_metadata_v*.json`` alongside it) rather than silently
clobbering history.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.models.xgboost_model import DualComponentXGBModel

_VERSION_PATTERN = re.compile(r"^xgboost_dlmo_sin_v(\d+)\.pkl$")


@dataclass
class ModelMetadata:
    model_version: str
    model_type: str
    feature_manifest_version: str
    feature_count: int
    training_date: str
    training_participant_count: int
    training_window_count: int
    test_participant_count: int
    test_window_count: int
    hyperparameters: dict
    split_seed: int
    split_version: str
    cv_metrics: dict
    test_metrics: dict
    baseline_metrics: dict
    library_versions: dict = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def next_version(models_dir: Path) -> int:
    models_dir = Path(models_dir)
    if not models_dir.exists():
        return 1
    versions = [
        int(m.group(1))
        for f in models_dir.iterdir()
        if (m := _VERSION_PATTERN.match(f.name))
    ]
    return max(versions, default=0) + 1


def save_model_artifacts(
    model: DualComponentXGBModel, metadata: ModelMetadata, models_dir: Path, version: int
) -> dict:
    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)

    sin_path = models_dir / f"xgboost_dlmo_sin_v{version}.pkl"
    cos_path = models_dir / f"xgboost_dlmo_cos_v{version}.pkl"
    metadata_path = models_dir / f"model_metadata_v{version}.json"

    if sin_path.exists() or cos_path.exists() or metadata_path.exists():
        raise FileExistsError(
            f"Model artifacts for version {version} already exist under {models_dir}. "
            "Model artifacts are never overwritten; use next_version() to pick a fresh version."
        )

    model.save(sin_path, cos_path)
    metadata_path.write_text(json.dumps(metadata.to_dict(), indent=2, default=str), encoding="utf-8")

    return {"sin_model": sin_path, "cos_model": cos_path, "metadata": metadata_path}


def load_model_artifacts(models_dir: Path, version: int, feature_names: tuple) -> tuple:
    models_dir = Path(models_dir)
    sin_path = models_dir / f"xgboost_dlmo_sin_v{version}.pkl"
    cos_path = models_dir / f"xgboost_dlmo_cos_v{version}.pkl"
    metadata_path = models_dir / f"model_metadata_v{version}.json"

    model = DualComponentXGBModel.load(sin_path, cos_path, feature_names)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return model, metadata
