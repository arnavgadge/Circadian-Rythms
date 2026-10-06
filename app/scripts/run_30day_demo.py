"""Runs the real CircadianIQ pipeline, day by day, over the deterministic
30-day demo participant (id=9001) seeded by `app.scripts.seed_30day_demo`.

    python -m app.scripts.seed_30day_demo --reset
    python -m app.scripts.run_30day_demo

For each day from day 7 (the first day with a full 6-day trailing
window) through day 30, in strict chronological order, this script:

    1. calls app.pipeline.orchestrator.run_daily_inference  (real feature
       engine -> XGBoost -> state engine -> fusion -> alignment ->
       contributors -> recommendation, one atomic write)
    2. calls app.safety.engine.SafetyEngine.evaluate            (real
       confidence gate + pattern detection), exactly as
       app.api.services.inference_service.InferenceService does
    3. backfills that day's own intervention_log compliance via
       app.effectiveness.backfill.backfill_compliance -- computed from
       the day's ACTUAL observed behavior vs. the target that was set,
       never a hard-coded compliance number
    4. once compliance history exists, calls
       app.personalization.update.update_personalization_state
       (as_of_date = day+1, so it only ever uses data through day's own
       just-backfilled compliance -- never a future day)

No step here computes a domain result itself -- every DLMO estimate,
alignment score, contributor ranking, recommendation, compliance
value, and personalization phase is a genuine, unmodified output of
the existing Phase 4-14 pipeline given this participant's predefined
(but otherwise ordinary) daily_observations rows. If you change this
script to write to `circadian_labels`, `alignment_results`,
`contributor_results`, `recommendations`/`intervention_log`, or
`personal_effect_models` directly, you have broken the demo's central
guarantee -- don't.

Outputs (all under release/demo_30day/, all derived from the run above):
    daily_summary.csv, journey_summary.json, demo_story.md,
    checkpoints/checkpoint_day_{7,10,18,24,30}.json, figures/*.png
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import date as date_cls, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEMO_PARTICIPANT_ID = 9001
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "demo_30day_story.db"
STORY_START_DATE = date_cls(2026, 4, 6)  # must match app.scripts.seed_30day_demo
OUTPUT_DIR = PROJECT_ROOT / "release" / "demo_30day"
CHECKPOINT_DAYS = (7, 10, 18, 24, 30)

STAGE_BY_DAY = {}
for d in range(1, 8):
    STAGE_BY_DAY[d] = "STAGE_1_BASELINE"
for d in range(8, 11):
    STAGE_BY_DAY[d] = "STAGE_2_IDENTIFY"
for d in range(11, 19):
    STAGE_BY_DAY[d] = "STAGE_3_CHANGE"
for d in range(19, 25):
    STAGE_BY_DAY[d] = "STAGE_4_RESPONSE"
for d in range(25, 31):
    STAGE_BY_DAY[d] = "STAGE_5_STABLE"


def _day_index(target_date: date_cls) -> int:
    return (target_date - STORY_START_DATE).days + 1


def run(db_path: Path) -> dict:
    import os

    os.environ["CIRCADIANIQ_DATABASE_URL"] = f"sqlite:///{db_path}"

    from sqlalchemy import select

    from app.config.settings import load_config
    from app.database.engine import create_app_engine, create_session_factory
    from app.database.models import CircadianLabel, InterventionLog, PersonalEffectModel, Recommendation
    from app.effectiveness.backfill import backfill_compliance
    from app.personalization.update import update_personalization_state
    from app.pipeline.orchestrator import run_daily_inference
    from app.safety.engine import RecommendationInput, SafetyEngine
    from app.synthetic.time_utils import clock_time_to_hour

    app_config = load_config()
    engine = create_app_engine(app_config)
    session_factory = create_session_factory(engine)

    daily_rows = []
    checkpoints = {}

    for day in range(7, 31):
        target_date = STORY_START_DATE + timedelta(days=day - 1)

        result = run_daily_inference(DEMO_PARTICIPANT_ID, target_date, session_factory)

        safety_session = session_factory()
        confidence_label = None
        highest_severity = None
        if result.status == "SUCCESS" and result.fusion_result is not None:
            rec_input = None
            if result.recommendation_result is not None and result.recommendation_result.primary is not None:
                primary = result.recommendation_result.primary
                rec_input = RecommendationInput(intervention_type=primary.intervention_type, text=primary.text)
            safety_engine = SafetyEngine()
            safety_engine.evaluate(
                safety_session, DEMO_PARTICIPANT_ID, target_date, result.fusion_result, result.alignment_result, rec_input, persist=True
            )
            safety_session.commit()
            confidence_label = str(result.fusion_result.confidence_label).split(".")[-1].lower()

        # --- backfill today's own compliance from today's own actual behavior ---
        compliance_degree = None
        intervention_type_for_today = None
        log_row = safety_session.execute(
            select(InterventionLog).where(InterventionLog.participant_id == DEMO_PARTICIPANT_ID, InterventionLog.log_date == target_date)
        ).scalar_one_or_none()
        if log_row is not None:
            recommendation_row = safety_session.get(Recommendation, log_row.recommendation_id)
            intervention_type_for_today = recommendation_row.intervention_type
            observation = None
            from app.database.models import DailyObservation

            observation = safety_session.execute(
                select(DailyObservation).where(DailyObservation.participant_id == DEMO_PARTICIPANT_ID, DailyObservation.observation_date == target_date)
            ).scalar_one_or_none()
            backfilled = backfill_compliance(log_row, recommendation_row, observation)
            if backfilled.applied:
                compliance_degree = backfilled.compliance.compliance_degree
            safety_session.commit()

        # --- personalization update, as_of tomorrow (never leaks today's own future) ---
        personalization_phase = None
        if intervention_type_for_today is not None:
            as_of = target_date + timedelta(days=1)
            outcome = update_personalization_state(safety_session, DEMO_PARTICIPANT_ID, intervention_type_for_today, as_of)
            model_row = safety_session.execute(
                select(PersonalEffectModel).where(
                    PersonalEffectModel.participant_id == DEMO_PARTICIPANT_ID,
                    PersonalEffectModel.intervention_type == intervention_type_for_today,
                )
            ).scalar_one_or_none()
            if model_row is not None:
                personalization_phase = model_row.personalization_phase

        # --- read back the committed label for this date for reporting ---
        label_row = safety_session.execute(
            select(CircadianLabel).where(CircadianLabel.participant_id == DEMO_PARTICIPANT_ID, CircadianLabel.target_date == target_date, CircadianLabel.is_latest.is_(True))
        ).scalar_one_or_none()

        row = {
            "day": day,
            "date": str(target_date),
            "stage": STAGE_BY_DAY[day],
            "pipeline_status": result.status,
            "sleep_onset": None,
            "screen_end": None,
            "morning_light_start": None,
            "last_meal": None,
            "fused_dlmo": str(label_row.fused_dlmo_time) if label_row and label_row.fused_dlmo_time else None,
            "xgb_dlmo": str(label_row.xgboost_dlmo_time) if label_row and label_row.xgboost_dlmo_time else None,
            "state_dlmo": str(label_row.state_model_dlmo_time) if label_row and label_row.state_model_dlmo_time else None,
            "alignment_score": result.alignment_result.final_score if result.alignment_result else None,
            "confidence": confidence_label,
            "top_contributor": (result.contributor_result.contributors[0].signal if result.contributor_result and result.contributor_result.contributors else None),
            "recommendation": (result.recommendation_result.primary.text if result.recommendation_result and result.recommendation_result.primary else None),
            "compliance_degree": compliance_degree,
            "personalization_phase": personalization_phase,
        }
        # fill in the day's own behavioral inputs for the report (read-only display)
        obs = safety_session.execute(
            select(DailyObservation).where(DailyObservation.participant_id == DEMO_PARTICIPANT_ID, DailyObservation.observation_date == target_date)
        ).scalar_one_or_none()
        if obs is not None:
            row["sleep_onset"] = str(obs.sleep_onset_time) if obs.sleep_onset_time else None
            row["screen_end"] = str(obs.evening_screen_end_time) if obs.evening_screen_end_time else None
            row["morning_light_start"] = str(obs.morning_light_start_time) if obs.morning_light_start_time else None
            row["last_meal"] = str(obs.last_meal_time) if obs.last_meal_time else None

        daily_rows.append(row)
        safety_session.close()
        print(f"day {day:2d} ({target_date}) [{STAGE_BY_DAY[day]}]: status={result.status} "
              f"alignment={row['alignment_score']} confidence={confidence_label} "
              f"top_contributor={row['top_contributor']} compliance={compliance_degree} phase={personalization_phase}")

        if day in CHECKPOINT_DAYS:
            checkpoints[day] = {
                "day": day,
                "date": str(target_date),
                "stage": STAGE_BY_DAY[day],
                "fused_dlmo": row["fused_dlmo"],
                "alignment_score": row["alignment_score"],
                "alignment_components": (
                    {name: comp.score for name, comp in result.alignment_result.behavioral_components.items()}
                    if result.alignment_result else None
                ),
                "contributors": (
                    [
                        {"rank": c.rank, "signal": c.signal, "direction": c.direction, "score": c.contributor_score}
                        for c in result.contributor_result.contributors
                    ]
                    if result.contributor_result else []
                ),
                "recommendation": row["recommendation"],
                "confidence": confidence_label,
                "compliance_degree": compliance_degree,
                "personalization_phase": personalization_phase,
            }

    engine.dispose()
    return {"daily_rows": daily_rows, "checkpoints": checkpoints}


def write_reports(data: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoints_dir = OUTPUT_DIR / "checkpoints"
    checkpoints_dir.mkdir(exist_ok=True)

    daily_rows = data["daily_rows"]
    fieldnames = list(daily_rows[0].keys())
    with (OUTPUT_DIR / "daily_summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(daily_rows)

    for day, checkpoint in data["checkpoints"].items():
        (checkpoints_dir / f"checkpoint_day_{day}.json").write_text(json.dumps(checkpoint, indent=2, default=str), encoding="utf-8")

    baseline_days = [r for r in daily_rows if r["day"] <= 10]
    final_days = [r for r in daily_rows if r["day"] >= 25]

    def _avg(rows, key):
        values = [r[key] for r in rows if r[key] is not None]
        return sum(values) / len(values) if values else None

    journey_summary = {
        "note": "This is a deterministic synthetic demonstration participant. All values below are real, unmodified outputs of the CircadianIQ pipeline given a predefined behavioral schedule -- not fabricated or hand-tuned.",
        "participant_id": DEMO_PARTICIPANT_ID,
        "scenario_id": "late_screen_recovery_30d",
        "day_range": [daily_rows[0]["day"], daily_rows[-1]["day"]],
        "baseline_mean_alignment": _avg(baseline_days, "alignment_score"),
        "final_mean_alignment": _avg(final_days, "alignment_score"),
        "checkpoints": data["checkpoints"],
    }
    (OUTPUT_DIR / "journey_summary.json").write_text(json.dumps(journey_summary, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {OUTPUT_DIR / 'daily_summary.csv'}, journey_summary.json, and {len(data['checkpoints'])} checkpoint files.")


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db-path", type=str, default=str(DEFAULT_DB_PATH))
    args = parser.parse_args(argv)

    db_path = Path(args.db_path)
    if not db_path.exists():
        raise SystemExit(f"{db_path} does not exist. Run `python -m app.scripts.seed_30day_demo --reset` first.")

    data = run(db_path)
    write_reports(data)
    print("\nDone. Next: python -m app.scripts.generate_30day_demo_figures  (figures + demo_story.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
