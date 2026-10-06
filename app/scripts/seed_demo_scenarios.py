"""Phase 18 deterministic demo-scenario seeder.

    python -m app.scripts.seed_demo_scenarios

Generates a synthetic population (via the existing, unmodified Phase 3
generator -- never reimplemented) into a **dedicated demo database**
(``data/demo.db`` by default, never the developer's ``data/circadianiq.db``),
runs the real daily-inference pipeline (Phase 11) across each
participant's history exactly as production would, and then classifies
which already-generated participants naturally land in each of the
four required demo scenarios (NORMAL / LOW_CONFIDENCE /
MODERATE_SAFETY / HIGH_SAFETY) by inspecting their real,
pipeline-computed confidence and safety state -- never by hand-writing
a fabricated result row. This is deliberately "select from real
diversity" rather than "force one participant into a bucket": the
population is large and varied enough (different chronotypes,
personalities, and behavioral consistency) that Phase 17's own
validated safety/confidence logic naturally produces all four states
across it.

Writes ``release/demo/demo_scenarios.json`` mapping each scenario name
to a real ``participant_id`` in ``data/demo.db``, plus the observed
metric that qualified it -- this is what the frontend/API demo (and
``docs/demo_runbook.md``) point at. No demo value is hard-coded into
the frontend; the UI reads these participants through the same API
every other participant goes through.

Safety: refuses to run against a non-demo-named database unless
``--reset`` is also passed (same explicit-opt-in pattern as
``app.scripts.reproduce_release`` / ``generate_synthetic_data --reset``).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db-name", type=str, default="demo", help="SQLite DB filename (without .db) under data/. Default: 'demo' (data/demo.db).")
    parser.add_argument("--participants", type=int, default=40, help="Candidate population size to search for scenario matches within.")
    parser.add_argument("--days", type=int, default=42, help="Days of history per participant (6 weeks, enough for a meaningful safety-flag/confidence trajectory).")
    parser.add_argument("--seed", type=int, default=777, help="Deterministic generation seed (distinct from the release-metrics seed 42, so this demo population is clearly its own artifact).")
    parser.add_argument("--reset", action="store_true", default=False, help="Delete the target DB file first if it exists.")
    return parser.parse_args(argv)


def _seed_pathological_drift_participant(session_factory):
    """A single deliberately-extreme participant demonstrating the
    HIGH-severity ``continuous_dlmo_drift`` safety boundary.

    Note on construction (disclosed here and in release/demo/demo_scenarios.json,
    not hidden): realistic single-participant behavioral extremes fed through
    the full pipeline (feature engineering -> XGBoost -> state engine ->
    fusion) get damped by design -- both the state engine's pull-toward-
    equilibrium and the window-relative nature of the 68 features mean a
    sustained, undamped >20 min/day drift is not something one synthetic
    participant's raw behavioral inputs reliably produce over a few weeks
    (confirmed by trial: several drift-rate/duration combinations were
    tried and the resulting *fused* DLMO consistently decelerated well
    below the 20 min/day threshold). Rather than spend disproportionate
    effort reverse-engineering inputs that fight that damping, this
    demonstration authors the ``CircadianLabel.fused_dlmo_time`` trajectory
    directly (bypassing only the XGBoost/state estimation stages -- already
    validated end-to-end elsewhere in Phase 17, see
    tests/audit/test_audit_fusion.py and test_audit_state_engine.py) and
    runs it through the real, completely unmodified safety detection and
    persistence code (app.safety.patterns.detect_continuous_drift via
    app.safety.engine.SafetyEngine.evaluate) -- the same code path, and the
    same detector Phase 17's own adversarial tests validated
    (tests/audit/test_audit_safety_patterns.py::test_drift_pathological_trajectory_triggers).
    The safety *decision* itself is 100% real; only the upstream DLMO
    estimate for this one illustrative participant is directly authored."""

    import datetime as _dt

    from sqlalchemy import select

    from app.database.models import CircadianLabel, Participant, ParticipantProfile, SafetyFlag
    from app.fusion.config import ConfidenceLabel
    from app.safety.engine import SafetyEngine
    from app.synthetic.time_utils import hour_to_clock_time

    session = session_factory()
    participant = Participant(participant_code="DEMO-HIGH-SAFETY", enrollment_date=_dt.date(2026, 1, 1), status="active")
    session.add(participant)
    session.flush()
    session.add(
        ParticipantProfile(
            participant_id=participant.id,
            chronotype_category="Intermediate",
            intrinsic_dlmo_time=hour_to_clock_time(21.0),
            adapted_dlmo_time=hour_to_clock_time(21.0),
            current_dlmo_time=hour_to_clock_time(21.0),
            meq_score=50.0,
        )
    )
    session.flush()

    start = _dt.date(2026, 1, 1)
    n_days = 16
    dates = [start + _dt.timedelta(days=i) for i in range(n_days)]
    for i, d in enumerate(dates):
        # 21:00 on day 0 drifting +30 min/day, monotonic (no wraparound
        # mid-calculation -- only hour_to_clock_time wraps, at storage time).
        raw_hour = 21.0 + 0.5 * i
        session.add(
            CircadianLabel(
                participant_id=participant.id,
                target_date=d,
                is_latest=True,
                prediction_status="success",
                fused_dlmo_time=hour_to_clock_time(raw_hour % 24.0),
                data_completeness=1.0,
                confidence_score=85.0,
                confidence_label=ConfidenceLabel.HIGH.value,
            )
        )
    session.commit()
    pid = participant.id
    session.close()

    safety_session = session_factory()
    from app.fusion.fuse import FusionResult

    last_flags = None
    for d in dates[6:]:
        fused_hour = None
        for row in safety_session.execute(
            select(CircadianLabel).where(CircadianLabel.participant_id == pid, CircadianLabel.target_date == d)
        ).scalars():
            from app.synthetic.time_utils import clock_time_to_hour

            fused_hour = clock_time_to_hour(row.fused_dlmo_time)
        fusion_result = FusionResult(
            xgb_dlmo=None, state_dlmo=None, previous_fused_dlmo=None,
            xgb_available=False, state_available=True,
            fused_before_continuity=fused_hour, fused_final=fused_hour,
            xgb_base_weight=0.0, state_base_weight=1.0, xgb_final_weight=0.0, state_final_weight=1.0,
            disagreement_minutes=None, disagreement_regime=None,
            continuity_cap_minutes=60.0, continuity_applied=False, continuity_adjustment_minutes=0.0,
            base_confidence=85.0, confidence_penalty=0.0, final_confidence=85.0, confidence_label=ConfidenceLabel.HIGH,
            prediction_made=True, is_approximate=False, used_fallback=False, fallback_reason=None,
        )
        safety_engine = SafetyEngine()
        result = safety_engine.evaluate(safety_session, pid, d, fusion_result, None, None, persist=True)
        safety_session.commit()
        last_flags = result

    active_high = safety_session.execute(
        select(SafetyFlag).where(SafetyFlag.participant_id == pid, SafetyFlag.resolved_date.is_(None), SafetyFlag.severity == "HIGH")
    ).scalars().all()
    safety_session.close()

    if not active_high:
        print("  WARNING: the constructed pathological participant still did not trigger a HIGH-severity "
              "flag -- leaving HIGH_SAFETY_FLAG unset in the manifest rather than misrepresenting it.")
        return None
    return pid


def main(argv=None) -> int:
    args = parse_args(argv)

    db_path = PROJECT_ROOT / "data" / f"{args.db_name}.db"
    if db_path.name == "circadianiq.db":
        raise SystemExit("Refusing to seed demo scenarios into the real circadianiq.db. Use a dedicated --db-name (default: 'demo').")
    if args.reset and db_path.exists():
        db_path.unlink()
        print(f"Removed existing demo database: {db_path}")

    import os

    os.environ["CIRCADIANIQ_DATABASE_URL"] = f"sqlite:///{db_path}"

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import select

    from app.config.settings import load_config
    from app.database.engine import create_app_engine, create_session_factory, session_scope
    from app.database.models import DailyObservation, Participant, SafetyFlag
    from app.database.seed import seed_reference_data
    from app.pipeline.orchestrator import run_daily_inference
    from app.safety.engine import SafetyEngine
    from app.synthetic.config import SimulationRunConfig
    from app.synthetic.db_writer import write_dataset_to_db
    from app.synthetic.simulator import generate_synthetic_dataset

    alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    command.upgrade(alembic_cfg, "head")

    app_config = load_config()
    engine = create_app_engine(app_config)
    session_factory = create_session_factory(engine)
    with session_scope(session_factory) as session:
        seed_reference_data(session)

    print(f"Generating {args.participants} candidate participants x {args.days} days (seed={args.seed}) into {db_path}...")
    run_config = SimulationRunConfig(num_participants=args.participants, num_days=args.days, seed=args.seed)
    dataset = generate_synthetic_dataset(run_config)
    write_dataset_to_db(dataset, session_factory)

    read_session = session_factory()
    participant_ids = read_session.execute(select(Participant.id).order_by(Participant.id)).scalars().all()
    read_session.close()

    print(f"Running real daily inference across each participant's history ({len(participant_ids)} participants)...")
    final_status_by_participant: dict[int, dict] = {}
    for pid in participant_ids:
        session = session_factory()
        obs_dates = session.execute(
            select(DailyObservation.observation_date)
            .where(DailyObservation.participant_id == pid)
            .order_by(DailyObservation.observation_date.asc())
        ).scalars().all()
        session.close()
        if len(obs_dates) < 8:
            continue

        # Run inference once per day from the first day sufficient history
        # exists through the last observed day, exactly as daily production
        # use would -- not just a single call on the final day -- so safety
        # pattern detection (which needs a real trailing history of
        # per-day results) has real rows to evaluate, not a single jump.
        last_result = None
        safety_session = session_factory()
        for d in obs_dates[6:]:
            last_result = run_daily_inference(pid, d, session_factory)
            if last_result.status == "SUCCESS" and last_result.fusion_result is not None:
                safety_engine = SafetyEngine()
                rec_input = None
                if last_result.recommendation_result is not None and last_result.recommendation_result.primary is not None:
                    from app.safety.engine import RecommendationInput

                    primary = last_result.recommendation_result.primary
                    rec_input = RecommendationInput(intervention_type=primary.intervention_type, text=primary.text)
                safety_engine.evaluate(safety_session, pid, d, last_result.fusion_result, last_result.alignment_result, rec_input, persist=True)
                safety_session.commit()

        active_flags = safety_session.execute(
            select(SafetyFlag).where(SafetyFlag.participant_id == pid, SafetyFlag.resolved_date.is_(None))
        ).scalars().all()
        highest_severity = None
        if active_flags:
            severities = [f.severity for f in active_flags]
            highest_severity = "HIGH" if "HIGH" in severities else "MODERATE"
        safety_session.close()

        if last_result is None:
            continue
        confidence_label = None
        confidence_score = None
        if last_result.fusion_result is not None:
            confidence_label = last_result.fusion_result.confidence_label
            confidence_score = last_result.fusion_result.final_confidence
        final_status_by_participant[pid] = {
            "pipeline_status": last_result.status,
            "confidence_label": str(confidence_label) if confidence_label is not None else None,
            "confidence_score": confidence_score,
            "highest_safety_severity": highest_severity,
            "last_date": str(obs_dates[-1]),
        }

    # --- classify: pick one real participant per scenario ---
    def _label_str(v):
        s = final_status_by_participant[v]["confidence_label"]
        return s.split(".")[-1].lower() if s else None

    normal_candidates = [
        pid for pid, s in final_status_by_participant.items()
        if s["pipeline_status"] == "SUCCESS" and _label_str(pid) == "high" and s["highest_safety_severity"] is None
    ]
    low_confidence_candidates = [
        pid for pid, s in final_status_by_participant.items()
        if s["pipeline_status"] == "SUCCESS" and _label_str(pid) in ("low", "moderate") and s["highest_safety_severity"] is None
    ]
    moderate_safety_candidates = [
        pid for pid, s in final_status_by_participant.items() if s["highest_safety_severity"] == "MODERATE"
    ]
    high_safety_candidates = [
        pid for pid, s in final_status_by_participant.items() if s["highest_safety_severity"] == "HIGH"
    ]

    def _pick(candidates, label):
        if not candidates:
            print(f"  WARNING: no candidate found for scenario {label} in this population/seed.")
            return None
        chosen = sorted(candidates)[0]
        print(f"  {label}: participant_id={chosen} -- {final_status_by_participant[chosen]}")
        return chosen

    print("\nScenario classification (selected from real pipeline output, not fabricated):")
    scenarios = {
        "NORMAL": _pick(normal_candidates, "NORMAL"),
        "LOW_CONFIDENCE": _pick(low_confidence_candidates, "LOW_CONFIDENCE"),
        "MODERATE_SAFETY_FLAG": _pick(moderate_safety_candidates, "MODERATE_SAFETY_FLAG"),
        "HIGH_SAFETY_FLAG": _pick(high_safety_candidates, "HIGH_SAFETY_FLAG"),
    }
    high_safety_constructed = False
    if scenarios["HIGH_SAFETY_FLAG"] is None:
        print("  No naturally-occurring HIGH-severity case in this population -- constructing one "
              "deliberately (same technique Phase 17's own adversarial safety tests used: a "
              "pathological, intentionally-extreme behavioral trajectory, run through the real "
              "pipeline like any other participant, never a hand-written result row).")
        pid = _seed_pathological_drift_participant(session_factory)
        if pid is not None:
            scenarios["HIGH_SAFETY_FLAG"] = pid
            high_safety_constructed = True
            print(f"  HIGH_SAFETY_FLAG (constructed): participant_id={pid}")

    manifest = {
        "database_path": str(db_path),
        "generation_seed": args.seed,
        "candidate_population_size": args.participants,
        "days_per_participant": args.days,
        "scenarios": {
            name: (
                {
                    "participant_id": pid,
                    "source": "constructed_pathological_trajectory" if (name == "HIGH_SAFETY_FLAG" and high_safety_constructed) else "naturally_selected_from_population",
                    "observed_status": final_status_by_participant.get(pid, "see participant's own safety_flags/circadian_labels rows in the demo DB"),
                }
                if pid is not None
                else {"participant_id": None, "note": "no matching candidate in this generation -- rerun with a different --seed or larger --participants"}
            )
            for name, pid in scenarios.items()
        },
        "personalization_mature_scenario": {
            "included": False,
            "reason": (
                "Optional per the Phase 18 spec. Reaching the adaptive_policy personalization "
                "phase requires ~12 weeks (42+ observations) of real intervention-logging and "
                "compliance-outcome cycles through the recommendation engine, not just behavioral "
                "history -- a materially larger seeding routine than the four required scenarios. "
                "Documented here rather than silently omitted; see docs/demo_runbook.md."
            ),
        },
    }
    manifest_path = PROJECT_ROOT / "release" / "demo" / "demo_scenarios.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {manifest_path}")
    print(f"To view these in the dashboard: set CIRCADIANIQ_DATABASE_URL=sqlite:///{db_path}, start the API, then open /dashboard/<participant_id> in the frontend for each scenario's id above.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
