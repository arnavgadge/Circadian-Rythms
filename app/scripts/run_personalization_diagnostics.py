"""CLI for the Phase 13 personalization diagnostic experiment.

Run with:

    python -m app.scripts.run_personalization_diagnostics

Builds a fresh database with a handful of controlled synthetic
participant/intervention histories (the same kind of harness Phase 12
introduced, since no earlier phase generates intervention history
automatically), checks personalization-phase graduation at several
points in time (demonstrating cold-start -> personalized transition
and independent per-intervention-type graduation), then runs a
**separate, in-memory** contextual-bandit simulation (two arms with
known, different true reward means) to verify Thompson sampling
increasingly favors the better arm while retaining some exploration.

**Everything reported here is a property of this synthetic harness /
simulated environment** -- never a claim about real participants.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import AppConfig
from app.database.engine import create_app_engine, create_session_factory
from app.database.init_db import create_all_tables
from app.database.models import AlignmentResult, CircadianLabel, DailyObservation, InterventionLog, Participant, ParticipantProfile, Recommendation
from app.logging_config import setup_logging
from app.personalization.bandit import ArmPosterior, select_action, update_posterior
from app.personalization.config import DEFAULT_PERSONALIZATION_CONFIG
from app.personalization.db_adapter import count_compliance_observations
from app.personalization.diagnostics import BanditSimulationResult, PhaseSnapshot, summarize_bandit_simulation, summarize_phase_snapshots
from app.personalization.dispatcher import get_personalization_phase
from app.synthetic.time_utils import hour_to_clock_time, normalize_hour

_TYPE_METADATA = {
    "screen": {
        "contributor_signals": ["evening_screen"], "value_kind": "clock_hour", "direction": "earlier",
        "template": "Try stopping screens by {target_time}.", "desired_value_assumption": -0.5,
        "desired_value_relative_to": "ideal_sleep_onset", "max_shift_per_recommendation": 1.5,
        "baseline_feasibility": 0.5, "is_literature_verified": False,
    },
    "light": {
        "contributor_signals": ["morning_light"], "value_kind": "duration_minutes", "direction": "increase",
        "template": "Try getting {target_value} of light.", "desired_value_assumption": 30.0,
        "desired_value_relative_to": None, "max_shift_per_recommendation": 15.0,
        "baseline_feasibility": 0.65, "is_literature_verified": False,
    },
}


def _build_history(session, participant_id, recommendation_id, intervention_type, start_date, n_days, true_effect, compliance_fn):
    dlmo = 21.0
    for i in range(n_days):
        d = start_date + timedelta(days=i)
        compliance = compliance_fn(i)
        dlmo = normalize_hour(dlmo + (true_effect * compliance) / 60.0)

        kwargs = dict(
            participant_id=participant_id, observation_date=d, sleep_onset_time=hour_to_clock_time(dlmo + 2.0),
            morning_light_duration_minutes=20.0, evening_screen_duration_minutes=180.0,
            last_meal_time=hour_to_clock_time(22.0), exercise_time=hour_to_clock_time(18.0),
            last_caffeine_time=hour_to_clock_time(10.0), caffeine_amount_mg=0.0,
        )
        if intervention_type == "screen":
            kwargs["evening_screen_duration_minutes"] = (1.0 - compliance) * 180.0 + 0.1
        elif intervention_type == "light":
            kwargs["morning_light_duration_minutes"] = 10.0 + compliance * 40.0

        session.add(DailyObservation(**kwargs))
        session.flush()
        label = CircadianLabel(
            participant_id=participant_id, target_date=d, is_latest=True, prediction_status="success",
            fused_dlmo_time=hour_to_clock_time(dlmo), data_completeness=1.0,
        )
        session.add(label)
        session.flush()
        session.add(
            AlignmentResult(
                circadian_label_id=label.id, participant_id=participant_id, target_date=d,
                final_alignment_score=60.0, phase_alignment_score=60.0, behavioral_alignment_score=60.0,
            )
        )
        session.add(
            InterventionLog(
                participant_id=participant_id, recommendation_id=recommendation_id, log_date=d,
                recommendation_text="test", target_value_time=hour_to_clock_time(21.5),
                compliance_degree=compliance, compliance_binary=compliance >= 0.65,
                expected_improvement_minutes=15.0, personalization_phase="literature",
            )
        )
    session.commit()


def _run_phase_snapshots(session_factory) -> list:
    session = session_factory()
    participant = Participant(participant_code="DIAG-PERS-001", enrollment_date=date(2026, 1, 1), status="active")
    session.add(participant)
    session.flush()
    session.add(
        ParticipantProfile(
            participant_id=participant.id, chronotype_category="Intermediate",
            intrinsic_dlmo_time=hour_to_clock_time(21.0), adapted_dlmo_time=hour_to_clock_time(21.0),
            current_dlmo_time=hour_to_clock_time(21.0),
        )
    )
    screen_rec = Recommendation(
        intervention_code="DIAG_PERS_SCREEN", intervention_type="screen", title="Test screen",
        target_behavior="screen", literature_expected_improvement_minutes=15.0, source="diagnostic harness",
        extra_metadata=_TYPE_METADATA["screen"],
    )
    session.add(screen_rec)
    session.flush()

    start = date(2026, 1, 1)
    _build_history(session, participant.id, screen_rec.id, "screen", start, 90, -10.0, lambda i: (i % 10) / 10.0)

    checkpoints = [("week_1", 7), ("week_3", 21), ("week_6", 42), ("week_9", 63), ("week_13", 91)]
    snapshots = []
    for label, day_offset in checkpoints:
        as_of = start + timedelta(days=day_offset)
        phase = get_personalization_phase(session, participant.id, "screen", as_of)
        n_obs = count_compliance_observations(session, participant.id, "screen", as_of)
        snapshots.append(PhaseSnapshot(label, participant.id, "screen", phase, n_obs))

    session.close()
    return snapshots


def _run_bandit_simulation(n_rounds: int = 300) -> BanditSimulationResult:
    rng = np.random.default_rng(42)
    config = DEFAULT_PERSONALIZATION_CONFIG
    true_means = {"morning_light": 18.0, "screen_reduction": 4.0}
    true_noise_sd = 5.0

    arms = {name: ArmPosterior(name, config.bandit_prior_mean, config.bandit_prior_variance, 0, 0.0) for name in true_means}
    selection_counts = {name: 0 for name in true_means}
    posterior_history = {name: [] for name in true_means}

    for round_index in range(n_rounds):
        chosen, _ = select_action(list(arms.values()), rng, config)
        selection_counts[chosen] += 1
        reward = float(rng.normal(true_means[chosen], true_noise_sd))
        arms[chosen] = update_posterior(arms[chosen], reward, config)
        for name, arm in arms.items():
            posterior_history[name].append((round_index, arm.posterior_mean, arm.posterior_variance))

    return BanditSimulationResult(n_rounds, selection_counts, posterior_history, true_means)


def main() -> int:
    setup_logging("INFO")
    db_path = PROJECT_ROOT / "data" / "processed" / "personalization_diagnostics.db"
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

    print("Building controlled synthetic participant history and checking phase graduation over time...")
    snapshots = _run_phase_snapshots(session_factory)
    phase_summary = summarize_phase_snapshots(snapshots)

    print("\n=== Cold-start -> personalized transition (one participant, one intervention type) ===")
    for snap in snapshots:
        print(f"  {snap.as_of_label}: n_observations={snap.n_observations} -> phase={snap.phase}")

    print("\nRunning a controlled contextual-bandit simulation (2 arms, known true means)...")
    bandit_result = _run_bandit_simulation()
    bandit_summary = summarize_bandit_simulation(bandit_result)

    print("\n=== Bandit simulation summary ===")
    for key, value in bandit_summary.items():
        print(f"{key}: {value}")

    output_dir = PROJECT_ROOT / "data" / "processed" / "personalization_diagnostics"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "personalization_diagnostics_summary.json").write_text(
        json.dumps({"phase_snapshots": phase_summary, "bandit_simulation": bandit_summary}, indent=2, default=str), encoding="utf-8"
    )
    print(f"\nSummary written to: {output_dir / 'personalization_diagnostics_summary.json'}")
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
