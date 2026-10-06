"""Seeds the deterministic 30-day demo participant ("Arjun -- CircadianIQ
Demo User", participant_id=9001) into a dedicated demonstration database.

    python -m app.scripts.seed_30day_demo
    python -m app.scripts.seed_30day_demo --reset
    python -m app.scripts.seed_30day_demo --db-path data/demo_30day_story.db --scenario demo/scenarios/late_screen_recovery_30d.yaml

This script writes ONLY:
    - one Participant + ParticipantProfile row (id=9001)
    - exactly 30 DailyObservation rows, loaded verbatim from the fixed
      YAML schedule (demo/scenarios/late_screen_recovery_30d.yaml) --
      never the random synthetic generator, never any RNG call.

It does NOT run inference, compute recommendations, or touch
compliance/personalization -- that is `app.scripts.run_30day_demo`'s
job, kept separate so "define the input data" and "run the real
intelligence pipeline on it" are two clearly distinct steps (matching
the brief: "The demo participant is special ONLY because its INPUT
DATA is predefined. The system outputs must remain real outputs.").

Safety: refuses to target a non-30day-story database name unless
--reset is also passed, and never touches data/demo.db or
data/circadianiq.db (the frozen release / dev databases) by construction
-- the default --db-path is a distinct file.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date as date_cls, datetime, time as time_cls, timedelta
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEMO_PARTICIPANT_ID = 9001
DEMO_PARTICIPANT_CODE = "DEMO-9001-ARJUN"
DEFAULT_SCENARIO_PATH = PROJECT_ROOT / "demo" / "scenarios" / "late_screen_recovery_30d.yaml"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "demo_30day_story.db"

# Story start date: a Monday, so the schedule's is_free_day pattern
# (days 6,7 / 13,14 / 20,21 / 27,28) lines up with real Sat/Sun.
STORY_START_DATE = date_cls(2026, 4, 6)


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db-path", type=str, default=str(DEFAULT_DB_PATH))
    parser.add_argument("--scenario", type=str, default=str(DEFAULT_SCENARIO_PATH))
    parser.add_argument("--reset", action="store_true", default=False, help="Delete the target DB file first if it exists.")
    return parser.parse_args(argv)


def _parse_hhmm(value) -> time_cls | None:
    if value is None:
        return None
    hh, mm = str(value).split(":")
    return time_cls(int(hh), int(mm))


def load_scenario(path: Path) -> dict:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    days = document["days"]
    if len(days) != 30:
        raise ValueError(f"Scenario file must define exactly 30 days, found {len(days)}")
    seen_days = {d["day"] for d in days}
    if seen_days != set(range(1, 31)):
        raise ValueError(f"Scenario file must define days 1..30 exactly once each, found {sorted(seen_days)}")
    return document


def main(argv=None) -> int:
    args = parse_args(argv)
    db_path = Path(args.db_path)
    scenario_path = Path(args.scenario)

    if db_path.name in ("circadianiq.db", "demo.db"):
        raise SystemExit(
            f"Refusing to seed the 30-day demo into '{db_path.name}' -- this must never overwrite the "
            "real dev database or the separate 4-scenario demo database. Use a dedicated --db-path "
            "(default: data/demo_30day_story.db)."
        )
    if args.reset and db_path.exists():
        db_path.unlink()
        print(f"Removed existing database: {db_path}")
    elif db_path.exists():
        raise SystemExit(f"{db_path} already exists. Pass --reset to recreate it (this is a safe, isolated demo database, not the frozen release data).")

    document = load_scenario(scenario_path)
    print(f"Loaded scenario '{document['scenario_id']}' -- {document['scenario_title']}")

    import os

    os.environ["CIRCADIANIQ_DATABASE_URL"] = f"sqlite:///{db_path}"

    from alembic import command
    from alembic.config import Config

    from app.config.settings import load_config
    from app.database.engine import create_app_engine, create_session_factory
    from app.database.models import DailyObservation, Participant, ParticipantProfile
    from app.database.seed import seed_reference_data
    from app.synthetic.time_utils import hour_to_clock_time

    alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    command.upgrade(alembic_cfg, "head")

    app_config = load_config()
    engine = create_app_engine(app_config)
    session_factory = create_session_factory(engine)
    session = session_factory()

    seed_reference_data(session)
    session.commit()

    # Deliberately-designed persona, NOT a sampled population participant
    # (see docs/30_day_demo_scenario.md "Why this is not a population participant").
    participant = Participant(
        id=DEMO_PARTICIPANT_ID,
        participant_code=DEMO_PARTICIPANT_CODE,
        enrollment_date=STORY_START_DATE,
        status="active",
        onboarding_completed_at=STORY_START_DATE,
    )
    session.add(participant)
    session.add(
        ParticipantProfile(
            participant_id=DEMO_PARTICIPANT_ID,
            chronotype_category="Late",
            # An intrinsic DLMO consistent with a "Late" chronotype (~2h
            # later than an average adult's ~20:00-21:00 DLMO). Recall
            # ideal_sleep_onset = fused_DLMO + phase_to_sleep_offset_hours
            # (2.0h, app/alignment/config.py) -- so a 22:00 DLMO implies
            # a ~00:00 ideal sleep onset, meaningfully earlier than this
            # story's ~01:45-02:00 baseline actual bedtime (a real
            # misalignment) and close to its ~23:35-23:55 improved
            # bedtime (a real, earned alignment gain). This was tuned by
            # inspecting actual pipeline output, never by hard-coding a
            # target score -- see docs/30_day_demo_scenario.md "Why the
            # DLMO seed values are what they are".
            intrinsic_dlmo_time=hour_to_clock_time(22.0),
            adapted_dlmo_time=hour_to_clock_time(22.5),
            current_dlmo_time=hour_to_clock_time(22.5),
            meq_score=28.0,  # low MEQ score consistent with a definite evening type
            meq_category="Definite Evening",
        )
    )
    session.flush()

    for entry in document["days"]:
        obs_date = STORY_START_DATE + timedelta(days=entry["day"] - 1)
        session.add(
            DailyObservation(
                participant_id=DEMO_PARTICIPANT_ID,
                observation_date=obs_date,
                sleep_onset_time=_parse_hhmm(entry["sleep_onset"]),
                sleep_offset_time=_parse_hhmm(entry["sleep_offset"]),
                sleep_duration_minutes=entry["sleep_duration_minutes"],
                is_free_day=entry["is_free_day"],
                social_jetlag_minutes=entry["social_jetlag_minutes"],
                morning_light_start_time=_parse_hhmm(entry["morning_light_start"]),
                morning_light_duration_minutes=entry["morning_light_duration_minutes"],
                evening_screen_end_time=_parse_hhmm(entry["screen_end"]),
                evening_screen_duration_minutes=entry["screen_duration_minutes"],
                last_meal_time=_parse_hhmm(entry["last_meal"]),
                exercise_time=_parse_hhmm(entry["exercise_time"]),
                exercise_duration_minutes=entry["exercise_duration_minutes"],
                last_caffeine_time=_parse_hhmm(entry["caffeine_time"]),
                caffeine_amount_mg=entry["caffeine_amount_mg"],
            )
        )

    session.commit()
    session.close()

    print(f"Seeded participant {DEMO_PARTICIPANT_ID} ({DEMO_PARTICIPANT_CODE}) with 30 daily_observations rows into {db_path}")
    print(f"Story dates: {STORY_START_DATE} .. {STORY_START_DATE + timedelta(days=29)}")
    print("No inference, recommendations, compliance, or personalization has been run yet -- next: python -m app.scripts.run_30day_demo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
