"""CLI for the Phase 12 effectiveness diagnostic experiment.

Run with:

    python -m app.scripts.run_effectiveness_diagnostics

Because Phase 3's synthetic generator produces no intervention/
compliance history automatically, this script is its own **controlled
simulation harness**: it builds a fresh database and injects a batch
of participants with known, hand-specified compliance patterns and
known true DLMO-shift-per-compliance-unit effects (some also with an
injected confound -- a second behavior that changes at the same time).

**This does not alter or fabricate anything in the core Phase 3
generator** -- it is a separate, explicitly-labeled harness whose
"true effect" values only exist here, for measuring how well
Phase 12's estimators recover a *known* answer. Real participants
never have a known true effect; see
``docs/intervention_effectiveness.md`` "Synthetic truth vs. estimated
effects".
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import AppConfig
from app.database.engine import create_app_engine, create_session_factory
from app.database.init_db import create_all_tables
from app.database.models import (
    AlignmentResult,
    CircadianLabel,
    DailyObservation,
    InterventionLog,
    Participant,
    ParticipantProfile,
    Recommendation,
)
from app.effectiveness.db_adapter import load_episodes, load_intervention_records, load_target_signal
from app.effectiveness.diagnostics import DiagnosticRun, summarize_effectiveness_batch
from app.effectiveness.dispatcher import evaluate_intervention_effect
from app.logging_config import setup_logging
from app.synthetic.time_utils import hour_to_clock_time, normalize_hour

_SCENARIOS = [
    # (true_effect_minutes, n_days, inject_confound)
    (-12.0, 35, False),
    (-8.0, 35, False),
    (6.0, 35, False),
    (-15.0, 10, False),  # too short for Phase 3 -- exercises the dispatcher's own gate
    (-10.0, 35, True),   # a confounding behavior (morning light) also changes
]


def _build_participant(session, index: int, true_effect: float, n_days: int, inject_confound: bool):
    base_date = date(2026, 1, 1)
    participant = Participant(participant_code=f"DIAG-{index:03d}", enrollment_date=base_date, status="active")
    session.add(participant)
    session.flush()

    session.add(
        ParticipantProfile(
            participant_id=participant.id, chronotype_category="Intermediate",
            intrinsic_dlmo_time=hour_to_clock_time(21.0), adapted_dlmo_time=hour_to_clock_time(21.0),
            current_dlmo_time=hour_to_clock_time(21.0),
        )
    )

    recommendation = Recommendation(
        intervention_code=f"DIAG_SCREEN_{index:03d}", intervention_type="screen", title="Reduce evening screen exposure",
        target_behavior="evening_screen_duration", literature_expected_improvement_minutes=15.0, source="diagnostic harness",
        extra_metadata={
            "contributor_signals": ["evening_screen"], "value_kind": "clock_hour", "direction": "earlier",
            "template": "Try stopping screens by {target_time}.", "desired_value_assumption": -0.5,
            "desired_value_relative_to": "ideal_sleep_onset", "max_shift_per_recommendation": 1.5,
            "baseline_feasibility": 0.5, "is_literature_verified": False,
        },
    )
    session.add(recommendation)
    session.flush()

    dlmo = 21.0
    for i in range(n_days):
        d = base_date + timedelta(days=i)
        is_intervention_day = i >= 7
        if is_intervention_day:
            compliance = ((i - 7) % 10) / 10.0
            dlmo = normalize_hour(dlmo + (true_effect * compliance) / 60.0)

        morning_light = 50.0 + (25.0 * math.sin(i / 3.0) if (inject_confound and is_intervention_day) else 2 * math.sin(i))

        session.add(
            DailyObservation(
                participant_id=participant.id, observation_date=d,
                sleep_onset_time=hour_to_clock_time(dlmo + 2.0),
                morning_light_duration_minutes=morning_light,
                evening_screen_duration_minutes=(0.5 * 60.0) if is_intervention_day else (3.0 * 60.0),
                last_meal_time=hour_to_clock_time(22.0 + 0.1 * math.cos(i)),
                exercise_time=hour_to_clock_time(18.0 + 0.1 * math.sin(i * 0.5)),
                last_caffeine_time=hour_to_clock_time(10.0), caffeine_amount_mg=0.0,
            )
        )
        session.flush()

        label = CircadianLabel(
            participant_id=participant.id, target_date=d, is_latest=True, prediction_status="success",
            fused_dlmo_time=hour_to_clock_time(dlmo), data_completeness=1.0,
        )
        session.add(label)
        session.flush()
        session.add(
            AlignmentResult(
                circadian_label_id=label.id, participant_id=participant.id, target_date=d,
                final_alignment_score=60.0 + i * 0.4, phase_alignment_score=60.0, behavioral_alignment_score=60.0,
            )
        )

        if is_intervention_day:
            compliance = ((i - 7) % 10) / 10.0
            session.add(
                InterventionLog(
                    participant_id=participant.id, recommendation_id=recommendation.id, log_date=d,
                    recommendation_text="Try stopping screens by 9:30 PM.", target_value_time=hour_to_clock_time(21.5),
                    compliance_degree=compliance, compliance_binary=compliance >= 0.65,
                    expected_improvement_minutes=15.0, personalization_phase="literature",
                )
            )

    session.commit()
    return participant.id, recommendation.id


def main() -> int:
    setup_logging("INFO")
    db_path = PROJECT_ROOT / "data" / "processed" / "effectiveness_diagnostics.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    config = AppConfig(
        environment="diagnostics", database_url=f"sqlite:///{db_path}",
        data_dir=PROJECT_ROOT / "data", raw_data_dir=PROJECT_ROOT / "data" / "raw",
        synthetic_data_dir=PROJECT_ROOT / "data" / "synthetic", processed_data_dir=PROJECT_ROOT / "data" / "processed",
        model_dir=PROJECT_ROOT / "models", log_level="INFO",
    )
    engine = create_app_engine(config)
    create_all_tables(engine)
    session_factory = create_session_factory(engine)

    print(f"Injecting {len(_SCENARIOS)} controlled intervention scenarios...")
    session = session_factory()
    scenario_ids = []
    for i, (true_effect, n_days, confound) in enumerate(_SCENARIOS):
        pid, rid = _build_participant(session, i, true_effect, n_days, confound)
        scenario_ids.append((pid, rid, true_effect))
    session.close()

    runs = []
    for pid, rid, true_effect in scenario_ids:
        session = session_factory()
        target_signal = load_target_signal(session, rid)
        episode = load_episodes(session, pid, rid)[-1]
        records = load_intervention_records(session, pid, rid)
        result = evaluate_intervention_effect(rid, pid, target_signal, episode, records)
        session.close()
        runs.append(DiagnosticRun(result=result, true_effect_minutes=true_effect))

    summary = summarize_effectiveness_batch(runs)

    print("\n=== Effectiveness diagnostic summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")

    output_dir = PROJECT_ROOT / "data" / "processed" / "effectiveness_diagnostics"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "effectiveness_diagnostics_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\nSummary written to: {output_dir / 'effectiveness_diagnostics_summary.json'}")
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
