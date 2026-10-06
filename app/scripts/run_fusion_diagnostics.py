"""CLI for the Phase 7 fusion diagnostic experiment.

Run with:

    python -m app.scripts.run_fusion_diagnostics

Runs fusion over the Phase 5 held-out test participants using the
trained XGBoost model's predictions and the Phase 6 state engine's
(replayed) estimates, and reports the required diagnostics: XGB-vs-
state disagreement distribution, regime frequencies, average final
weights, continuity-cap usage, confidence distribution, and the
XGB-error-vs-fused-error comparison.

**No fusion parameter is tuned against this test set** -- the Q26
weights/thresholds/caps are fixed, locked configuration
(``app.fusion.config.DEFAULT_FUSION_CONFIG``), read here only to
*apply*, never adjusted based on what this script observes.

See ``app.fusion.diagnostics`` for the important scientific caveat
about what this experiment can and cannot demonstrate on synthetic data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import load_config
from app.database.engine import create_app_engine, create_session_factory
from app.features.dataset import build_feature_dataset
from app.fusion.confidence import DataQualityInput
from app.fusion.config import DEFAULT_FUSION_CONFIG, DataQualityTier
from app.fusion.diagnostics import FusionInputRow, build_diagnostics_plots, run_fusion_over_windows, summarize_fusion_report
from app.logging_config import setup_logging
from app.models.config import DEFAULT_TRAINING_CONFIG
from app.models.model_registry import load_model_artifacts
from app.models.splitting import split_participants
from app.synthetic.config import DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC, SimulationRunConfig
from app.synthetic.simulator import generate_synthetic_dataset


def _completeness_to_tier(completeness: float) -> DataQualityTier:
    if completeness >= 0.95:
        return DataQualityTier.HIGH
    if completeness >= 0.80:
        return DataQualityTier.MODERATE
    if completeness >= 0.50:
        return DataQualityTier.LOW
    return DataQualityTier.VERY_LOW


def main() -> int:
    app_config = load_config()
    setup_logging(app_config.log_level)

    print("Regenerating the Phase 3 synthetic dataset (seed 42) for state-engine ground truth...")
    run_cfg = SimulationRunConfig(num_participants=1000, num_days=30, seed=42)
    synthetic_dataset = generate_synthetic_dataset(run_cfg, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)
    state_by_participant_and_date = {
        (int(row.participant_index), row.date): row.current_dlmo_hour
        for row in synthetic_dataset.daily_df.itertuples(index=False)
    }
    code_to_index = {
        row.participant_code: int(row.index) for row in synthetic_dataset.participants_df.itertuples(index=False)
    }

    print("Loading the trained Phase 5 XGBoost model (version 1)...")
    from app.features.feature_manifest import FEATURE_NAMES

    model, metadata = load_model_artifacts(PROJECT_ROOT / "models", version=1, feature_names=FEATURE_NAMES)

    engine = create_app_engine(app_config)
    session = create_session_factory(engine)()

    from app.database.models import Participant

    from sqlalchemy import select

    participant_rows = session.execute(select(Participant.id, Participant.participant_code)).all()
    id_to_code = {pid: code for pid, code in participant_rows}
    all_ids = list(id_to_code.keys())

    split = split_participants(all_ids, DEFAULT_TRAINING_CONFIG.split.test_fraction, DEFAULT_TRAINING_CONFIG.split.split_seed)
    print(f"Reproduced Phase 5 split: {len(split.train_ids)} train / {len(split.test_ids)} test participants.")

    print("Building Phase 4 features for the test participants...")
    dataset = build_feature_dataset(list(split.test_ids), session)
    session.close()

    xgb_predictions = model.predict_hours(dataset.X)

    rows = []
    for i in range(len(dataset.X)):
        meta = dataset.metadata.iloc[i]
        target = dataset.targets.iloc[i]
        participant_id = int(meta["participant_id"])
        participant_code = id_to_code[participant_id]
        participant_index = code_to_index[participant_code]
        state_dlmo = state_by_participant_and_date.get((participant_index, meta["target_date"]))

        rows.append(
            FusionInputRow(
                participant_id=participant_id,
                target_date=meta["target_date"],
                xgb_dlmo=float(xgb_predictions[i]),
                state_dlmo=state_dlmo,
                actual_dlmo=float(target["target_dlmo_hour"]),
                data_quality=DataQualityInput(
                    tier=_completeness_to_tier(meta["completeness"]),
                    window_completeness=meta["completeness"],
                    tier1_signals_missing=(meta["tier_1_missing"] >= 3),
                ),
            )
        )

    rows.sort(key=lambda r: (r.participant_id, r.target_date))

    print(f"Running fusion over {len(rows)} test windows...")
    fusion_df = run_fusion_over_windows(rows, DEFAULT_FUSION_CONFIG)
    summary = summarize_fusion_report(fusion_df)

    print("\n=== Fusion diagnostic summary ===")
    print(f"windows: {summary['n_windows']}")
    print(f"mean XGB final weight: {summary['mean_xgb_final_weight']:.3f}")
    print(f"mean state final weight: {summary['mean_state_final_weight']:.3f}")
    print(f"continuity caps applied: {summary['n_continuity_caps_applied']}")
    print(f"regime counts: {summary['disagreement_regime_counts']}")
    print(f"confidence label counts: {summary['confidence_label_counts']}")
    print(f"XGB MAE: {summary['xgb_mae_minutes']:.2f} min")
    print(f"Fused MAE: {summary['fused_mae_minutes']:.2f} min")
    print(f"Improvement: {summary['mae_improvement_minutes']:.2f} min")

    output_dir = PROJECT_ROOT / "data" / "processed" / "fusion_diagnostics"
    output_dir.mkdir(parents=True, exist_ok=True)
    fusion_df.to_parquet(output_dir / "fusion_results.parquet", index=False)
    (output_dir / "fusion_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    written = build_diagnostics_plots(fusion_df, output_dir / "plots")
    print(f"\nPlots written to: {output_dir / 'plots'}")
    for name, path in written.items():
        print(f"  {name}: {path}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
