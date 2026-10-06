"""CLI for the Phase 14 safety-layer diagnostic experiment.

Run with:

    python -m app.scripts.run_safety_diagnostics [--participants N]

Writes a Phase 3 synthetic population to a fresh database (real
chronotype/personality-driven DLMO trajectories), assigns each day a
synthetic confidence score (Phase 3 has no fusion step of its own, so
this diagnostic run assigns one purely to exercise Layer 1 -- never a
real confidence computation), then runs the full safety engine for
every participant at day 20 and reports the required distributions.

Also includes a dedicated midnight-edge-case check (a hand-built
trajectory oscillating around midnight with no real drift) and an
explicit "false-positive-like behavior" check under ordinary synthetic
variation, since the brief calls both out specifically.

**Every distribution here is a property of the synthetic system and
this run's synthetic confidence assignment -- never a claim about real
disease prevalence.**
"""

from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from app.config.settings import AppConfig
from app.database.engine import create_app_engine, create_session_factory
from app.database.init_db import create_all_tables
from app.database.models import CircadianLabel, Participant
from app.fusion.config import ConfidenceLabel
from app.logging_config import setup_logging
from app.safety.diagnostics import summarize_safety_diagnostics
from app.safety.engine import RecommendationInput, SafetyEngine
from app.synthetic.config import DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC, SimulationRunConfig
from app.synthetic.db_writer import write_dataset_to_db
from app.synthetic.simulator import generate_synthetic_dataset
from app.synthetic.time_utils import hour_to_clock_time, normalize_hour


def _confidence_label_for(score: float):
    if score >= 80:
        return ConfidenceLabel.HIGH
    if score >= 60:
        return ConfidenceLabel.MODERATE
    if score >= 40:
        return ConfidenceLabel.LOW
    return ConfidenceLabel.NO_PREDICTION


def _synthetic_fusion_result(rng, dlmo_hour):
    score = float(np.clip(rng.normal(78.0, 15.0), 10.0, 99.0))
    label = _confidence_label_for(score)
    prediction_made = label != ConfidenceLabel.NO_PREDICTION
    return type("FusionResult", (), {
        "prediction_made": prediction_made,
        "fused_final": dlmo_hour if prediction_made else None,
        "final_confidence": score,
        "confidence_label": label,
    })()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--participants", type=int, default=150)
    args = parser.parse_args()

    setup_logging("INFO")
    db_path = PROJECT_ROOT / "data" / "processed" / "safety_diagnostics.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    config = AppConfig(
        environment="diagnostics", database_url=f"sqlite:///{db_path}",
        data_dir=PROJECT_ROOT / "data", raw_data_dir=PROJECT_ROOT / "data" / "raw",
        synthetic_data_dir=PROJECT_ROOT / "data" / "synthetic", processed_data_dir=PROJECT_ROOT / "data" / "processed",
        model_dir=PROJECT_ROOT / "models", log_level="INFO",
    )
    engine_db = create_app_engine(config)
    create_all_tables(engine_db)
    session_factory = create_session_factory(engine_db)

    print(f"Generating {args.participants}-participant synthetic dataset (seed 42)...")
    run_cfg = SimulationRunConfig(num_participants=args.participants, num_days=30, seed=42)
    dataset = generate_synthetic_dataset(run_cfg, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)
    write_dataset_to_db(dataset, session_factory)

    rng = np.random.default_rng(42)
    session = session_factory()
    participants = session.execute(select(Participant.id, Participant.participant_code)).all()
    personality_by_id = {
        pid: row.personality_key
        for pid, row in zip(
            [p[0] for p in participants],
            dataset.participants_df.itertuples(index=False),
        )
    }
    chronotype_by_id = {
        pid: row.chronotype
        for pid, row in zip([p[0] for p in participants], dataset.participants_df.itertuples(index=False))
    }
    session.close()

    safety_engine = SafetyEngine()
    rows = []
    as_of_offset = timedelta(days=20)

    for pid, code in participants:
        session = session_factory()
        label = session.execute(
            select(CircadianLabel).where(CircadianLabel.participant_id == pid, CircadianLabel.target_date == dataset.generated_at.date() + as_of_offset)
        ).scalars().first()
        target_dlmo = None
        if label is not None:
            from app.synthetic.time_utils import clock_time_to_hour

            target_dlmo = clock_time_to_hour(label.fused_dlmo_time)
        as_of_date = dataset.generated_at.date() + as_of_offset

        fusion_result = _synthetic_fusion_result(rng, target_dlmo if target_dlmo is not None else 21.0)
        output = safety_engine.evaluate(
            session, pid, as_of_date, fusion_result,
            recommendation=RecommendationInput("screen", "Try stopping screens by 10:00 PM."),
        )
        session.close()

        rows.append(
            {
                "confidence_score": output.confidence_score,
                "confidence_label": output.confidence_label,
                "flags": [f.flag_type for f in output.active_safety_flags],
                "severities": [f.severity for f in output.active_safety_flags],
                "recommendation_suppressed": output.recommendation_suppressed,
                "chronotype": chronotype_by_id.get(pid),
                "personality_key": personality_by_id.get(pid),
            }
        )

    summary = summarize_safety_diagnostics(rows)

    print("\n=== Safety diagnostic summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")

    false_positive_rate = sum(1 for r in rows if r["flags"]) / len(rows) if rows else None
    print(f"\nflag rate under ordinary synthetic trajectories (screening false-positive-like rate): {false_positive_rate:.3f}")

    # Midnight edge-case check: a hand-built oscillating-but-stable trajectory must not flag drift.
    session = session_factory()
    midnight_participant = Participant(participant_code="SAFETY-DIAG-MIDNIGHT", enrollment_date=dataset.generated_at.date(), status="active")
    session.add(midnight_participant)
    session.flush()
    from app.database.models import ParticipantProfile

    session.add(
        ParticipantProfile(
            participant_id=midnight_participant.id, chronotype_category="Intermediate",
            intrinsic_dlmo_time=hour_to_clock_time(21.0), adapted_dlmo_time=hour_to_clock_time(21.0), current_dlmo_time=hour_to_clock_time(21.0),
        )
    )
    base = dataset.generated_at.date()
    for i in range(14):
        d = base + timedelta(days=i)
        h = 23.9167 if i % 2 == 0 else 0.0833
        session.add(CircadianLabel(participant_id=midnight_participant.id, target_date=d, is_latest=True, prediction_status="success", fused_dlmo_time=hour_to_clock_time(h), data_completeness=1.0))
    session.commit()

    midnight_output = safety_engine.evaluate(
        session, midnight_participant.id, base + timedelta(days=14),
        _synthetic_fusion_result(rng, 21.0),
    )
    midnight_flagged_drift = "continuous_dlmo_drift" in [f.flag_type for f in midnight_output.active_safety_flags]
    session.close()
    print(f"midnight-oscillation participant flagged for false drift: {midnight_flagged_drift} (expected False)")

    output_dir = PROJECT_ROOT / "data" / "processed" / "safety_diagnostics"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "safety_diagnostics_summary.json").write_text(
        json.dumps({**summary, "false_positive_like_rate": false_positive_rate, "midnight_edge_case_false_drift": midnight_flagged_drift}, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\nSummary written to: {output_dir / 'safety_diagnostics_summary.json'}")
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
