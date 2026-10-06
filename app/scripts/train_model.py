"""CLI for the CircadianIQ XGBoost DLMO training + validation pipeline.

Run with:

    python -m app.scripts.train_model

Reads the feature dataset directly from the database (Phase 4), runs
the full data-prep -> participant-split -> grouped-CV -> final-fit ->
held-out-test -> reporting pipeline, saves versioned model artifacts
under ``models/``, logs a ``training_runs`` row, and writes a report +
diagnostic plots under ``data/processed/model_evaluation/``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import load_config
from app.database.engine import create_app_engine, create_session_factory
from app.features.dataset import build_feature_dataset_for_all_participants
from app.logging_config import setup_logging
from app.models.config import DEFAULT_TRAINING_CONFIG
from app.models.diagnostics import build_diagnostics_plots
from app.models.training import persist_training_run, run_training_pipeline


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-shap", action="store_true", default=False, help="Skip SHAP importance computation.")
    parser.add_argument("--shap-sample-size", type=int, default=300)
    parser.add_argument(
        "--output-dir", type=str, default=str(PROJECT_ROOT / "data" / "processed" / "model_evaluation")
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    app_config = load_config()
    setup_logging(app_config.log_level)

    engine = create_app_engine(app_config)
    session_factory = create_session_factory(engine)
    session = session_factory()

    print("Loading the Phase 4 feature dataset from the database...")
    dataset = build_feature_dataset_for_all_participants(session)
    print(f"X shape: {dataset.X.shape}")

    print("Running training pipeline (split -> GroupKFold CV -> final fit -> held-out test)...")
    result = run_training_pipeline(
        dataset,
        session,
        DEFAULT_TRAINING_CONFIG,
        compute_shap=not args.no_shap,
        shap_sample_size=args.shap_sample_size,
    )

    print(f"\nTrain participants: {result.n_train_participants}  Test participants: {result.n_test_participants}")
    print(f"Train windows: {result.n_train_windows}  Test windows: {result.n_test_windows}")
    print(f"\nCV summary: MAE {result.cv_summary['mae_minutes_mean']:.1f} +/- {result.cv_summary['mae_minutes_std']:.1f} min")
    print(
        f"Held-out test: MAE {result.test_metrics.mae_minutes:.1f} min, "
        f"RMSE {result.test_metrics.rmse_minutes:.1f} min, "
        f"%within60 {result.test_metrics.pct_within_60_min:.1f}%"
    )
    print(f"Success target level reached: {result.success_target_level}")

    models_dir = PROJECT_ROOT / "models"
    persisted = persist_training_run(result, models_dir, session)
    print(f"\nSaved model version {persisted['version']} to {models_dir}")
    print(f"Logged training_runs row id={persisted['training_run_id']}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written_plots = build_diagnostics_plots(result, output_dir / "plots")
    print(f"\nDiagnostic plots written to: {output_dir / 'plots'}")

    summary = {
        "n_train_participants": result.n_train_participants,
        "n_test_participants": result.n_test_participants,
        "n_train_windows": result.n_train_windows,
        "n_test_windows": result.n_test_windows,
        "cv_summary": result.cv_summary,
        "test_metrics": result.test_metrics.to_dict(),
        "baseline_metrics": result.baseline_metrics,
        "success_target_level": result.success_target_level,
        "personality_metrics": result.personality_metrics.to_dict(orient="records"),
        "chronotype_metrics": result.chronotype_metrics.to_dict(orient="records"),
        "completeness_metrics": result.completeness_metrics.to_dict(orient="records"),
        "feature_importance_gain_top20": result.feature_importance_gain.head(20).to_dict(orient="records"),
        "shap_importance_top20": (
            result.shap_importance.head(20).to_dict(orient="records") if result.shap_importance is not None else None
        ),
        "model_version": persisted["version"],
        "training_run_id": persisted["training_run_id"],
    }
    summary_path = output_dir / "training_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"Summary written to: {summary_path}")

    session.close()
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
