"""Seed and process the DEMO-001 30-day synthetic research participant.

    python scripts/demo/seed_demo_participant.py --dry-run   # plan only, writes nothing
    python scripts/demo/seed_demo_participant.py             # seed + chronological inference
    python scripts/demo/seed_demo_participant.py --reset     # delete DEMO-001's rows only, then re-seed

Writes into the **configured** CircadianIQ database (``load_config()``,
i.e. ``CIRCADIANIQ_DATABASE_URL`` or the default ``data/circadianiq.db``)
-- never a separate database -- and only ever rows belonging to
participant DEMO-001.

What it does, in order:

1. Guards the target: refuses a production environment, a missing
   database file (never creates one), or a schema that isn't at the
   Alembic head (never migrates).
2. Generates 30 days of raw behavior deterministically
   (``demo_generator.py``) and validates every day with the API's own
   ``DailyEntryRequest`` model.
3. Creates or verifies participant DEMO-001 and upserts its 30
   ``daily_observations`` rows through the existing
   ``BehaviorRepository.upsert`` -- one transaction, rolled back on any
   error.
4. Runs the existing production inference path for days 7..30 in
   strict chronological order: ``InferenceService.run`` (exactly what
   ``POST /participants/{id}/inference`` executes: the Phase 11
   pipeline followed by the Phase 14 safety engine), then -- as the
   project's own ``app/scripts/run_30day_demo.py`` does -- the existing
   ``backfill_compliance`` for that day's intervention and the existing
   ``update_personalization_state`` (``as_of`` the next day, so nothing
   from the future is visible). This script computes no domain value.
5. Fingerprints every non-DEMO-001 row before and after, and reports
   whether anything outside DEMO-001 changed.
6. Writes ``scripts/demo/demo_manifest.json``.

Idempotent: re-running with an unchanged generator inserts nothing,
and every already-processed day short-circuits through the pipeline's
own idempotency check (so no second safety / compliance /
personalization pass runs for it).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import date as date_cls, datetime, time as time_cls, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, DEMO_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from demo_generator import (  # noqa: E402
    DEFAULT_SEED,
    DEFAULT_START_DATE,
    GENERATOR_VERSION,
    NUM_DAYS,
    GeneratedDay,
    PersonaTraits,
    dataset_checksum,
    generate,
)

DEMO_PARTICIPANT_ID = 9101
DEMO_PARTICIPANT_CODE = "DEMO-001"
DEMO_MARKER = "circadianiq-research-demo/DEMO-001"
DEMO_DESCRIPTION = "CircadianIQ Research Demo"
DEMO_LABEL = "SYNTHETIC RESEARCH PARTICIPANT"
FIRST_PREDICTION_DAY = 7  # first day with six complete prior days
ALLOWED_ENVIRONMENTS = {"development", "dev", "demo", "local", "test", "testing"}
MANIFEST_PATH = DEMO_DIR / "demo_manifest.json"

# Raw observation columns this script writes (no derived CircadianIQ result).
OBSERVATION_FIELDS = (
    "sleep_onset_time",
    "sleep_offset_time",
    "sleep_duration_minutes",
    "sleep_midpoint_time",
    "sleep_midpoint_variability_minutes",
    "is_free_day",
    "free_day_sleep_onset_time",
    "free_day_sleep_offset_time",
    "free_day_sleep_midpoint_time",
    "social_jetlag_minutes",
    "morning_light_start_time",
    "morning_light_duration_minutes",
    "evening_screen_end_time",
    "evening_screen_duration_minutes",
    "last_meal_time",
    "meal_to_sleep_gap_minutes",
    "exercise_time",
    "exercise_duration_minutes",
    "last_caffeine_time",
    "caffeine_amount_mg",
)
TIME_FIELDS = {f for f in OBSERVATION_FIELDS if f.endswith("_time")}


class DemoSeedError(RuntimeError):
    """A refusal or failure that must stop the run (nothing partial is left)."""


# --------------------------------------------------------------------------- helpers


def _parse_time(value: str | None) -> time_cls | None:
    if value is None:
        return None
    hh, mm = value.split(":")
    return time_cls(int(hh), int(mm))


def _row_fields(day: GeneratedDay) -> dict:
    data = asdict(day)
    return {f: (_parse_time(data[f]) if f in TIME_FIELDS else data[f]) for f in OBSERVATION_FIELDS}


def describe_target(database_url: str) -> dict:
    """Database identity without credentials."""

    from sqlalchemy.engine import make_url

    url = make_url(database_url)
    if url.get_backend_name() == "sqlite":
        db_path = Path(url.database or "")
        try:
            shown = str(db_path.resolve().relative_to(PROJECT_ROOT))
        except ValueError:
            shown = db_path.name
        return {"type": "sqlite", "database": shown.replace("\\", "/"), "path": db_path}
    return {"type": url.get_backend_name(), "database": url.database, "host": url.host, "path": None}


def guard_target(config, target: dict) -> None:
    env = (config.environment or "").strip().lower()
    if env not in ALLOWED_ENVIRONMENTS or "prod" in env:
        raise DemoSeedError(
            f"Refusing to seed: CIRCADIANIQ_ENV='{config.environment}' is not a development/demo environment "
            f"(allowed: {sorted(ALLOWED_ENVIRONMENTS)})."
        )
    if target["type"] == "sqlite":
        path: Path = target["path"]
        if not path.is_file():
            raise DemoSeedError(
                f"Configured database file {path} does not exist. This script never creates a database; "
                "initialise the configured one first (python scripts/init_db.py)."
            )


def guard_schema(engine) -> str:
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    if current != head:
        raise DemoSeedError(f"Database schema revision is {current!r}, expected Alembic head {head!r}. This script never migrates.")
    return current


def validate_days(days: list[GeneratedDay]) -> None:
    """Every day must pass the API's own daily-entry validation, and the
    30 dates must be consecutive and unique."""

    from app.api.schemas.daily_entry import DailyEntryRequest

    dates = [date_cls.fromisoformat(d.observation_date) for d in days]
    if len(days) != NUM_DAYS or len(set(dates)) != NUM_DAYS:
        raise DemoSeedError("Generator must produce exactly 30 unique dates.")
    for a, b in zip(dates, dates[1:]):
        if (b - a).days != 1:
            raise DemoSeedError(f"Dates are not consecutive: {a} -> {b}")
    for d in days:
        DailyEntryRequest(
            observation_date=d.observation_date,
            sleep_onset_time=d.sleep_onset_time,
            sleep_offset_time=d.sleep_offset_time,
            morning_light_start_time=d.morning_light_start_time,
            morning_light_duration_minutes=d.morning_light_duration_minutes,
            evening_screen_end_time=d.evening_screen_end_time,
            evening_screen_duration_minutes=d.evening_screen_duration_minutes,
            last_meal_time=d.last_meal_time,
            exercise_time=d.exercise_time,
            last_caffeine_time=d.last_caffeine_time,
            caffeine_amount_mg=d.caffeine_amount_mg,
            is_free_day=d.is_free_day,
        )


def participant_scoped_tables():
    from app.database.models import Base

    return [t for t in Base.metadata.sorted_tables if "participant_id" in t.c]


def foreign_fingerprint(session) -> dict:
    """Row count + SHA-256 of every row NOT belonging to DEMO-001, per
    table, ordered by primary key. Shared reference tables
    (``recommendations`` catalogue, ``training_runs``) are fingerprinted
    in full."""

    from sqlalchemy import select

    from app.database.models import Base

    out: dict = {}
    for table in Base.metadata.sorted_tables:
        stmt = select(table)
        if "participant_id" in table.c:
            stmt = stmt.where(table.c.participant_id != DEMO_PARTICIPANT_ID)
        elif table.name == "participants":
            stmt = stmt.where(table.c.id != DEMO_PARTICIPANT_ID)
        stmt = stmt.order_by(*table.primary_key.columns)
        digest = hashlib.sha256()
        count = 0
        for row in session.execute(stmt):
            digest.update(repr(tuple(row)).encode("utf-8"))
            count += 1
        out[table.name] = {"rows": count, "sha256": digest.hexdigest()}
    return out


def find_demo_participant(session):
    """Returns the verified DEMO-001 Participant, or None if absent.
    Raises if the reserved id / code is held by anything else."""

    from sqlalchemy import select

    from app.database.models import Participant, ParticipantProfile

    by_code = session.execute(select(Participant).where(Participant.participant_code == DEMO_PARTICIPANT_CODE)).scalars().first()
    by_id = session.get(Participant, DEMO_PARTICIPANT_ID)

    if by_code is None and by_id is None:
        return None
    if by_code is None or by_id is None or by_code.id != by_id.id:
        raise DemoSeedError(
            f"Reserved demo identity conflict: participant_code {DEMO_PARTICIPANT_CODE!r} -> "
            f"{getattr(by_code, 'id', None)}, id {DEMO_PARTICIPANT_ID} -> {getattr(by_id, 'participant_code', None)!r}. "
            "Refusing to touch either record."
        )
    profile = session.get(ParticipantProfile, DEMO_PARTICIPANT_ID)
    marker = (profile.synthetic_personality_profile or {}).get("demo_dataset") if profile else None
    if marker != DEMO_MARKER:
        raise DemoSeedError(
            f"Participant {DEMO_PARTICIPANT_CODE} exists but is not marked as this demonstration dataset "
            f"(marker={marker!r}). Refusing to modify it."
        )
    return by_id


# --------------------------------------------------------------------------- phases


def reset_demo(session) -> dict:
    """Delete DEMO-001's rows only (child tables first), in the caller's transaction."""

    from sqlalchemy import delete

    from app.database.models import Participant

    deleted: dict = {}
    for table in reversed(participant_scoped_tables()):
        result = session.execute(delete(table).where(table.c.participant_id == DEMO_PARTICIPANT_ID))
        if result.rowcount:
            deleted[table.name] = result.rowcount
    result = session.execute(delete(Participant.__table__).where(Participant.__table__.c.id == DEMO_PARTICIPANT_ID))
    if result.rowcount:
        deleted["participants"] = result.rowcount
    return deleted


def ensure_participant(session, persona: PersonaTraits, start: date_cls, seed: int, checksum: str) -> str:
    from app.database.models import Participant, ParticipantProfile
    from app.synthetic.time_utils import hour_to_clock_time

    existing = find_demo_participant(session)
    if existing is not None:
        profile = session.get(ParticipantProfile, DEMO_PARTICIPANT_ID)
        if profile.synthetic_personality_profile.get("dataset_checksum") != checksum:
            raise DemoSeedError(
                "DEMO-001 exists but was generated from a different dataset (seed/start date/generator changed). "
                "Run with --reset to rebuild it from the current generator."
            )
        return "verified existing"

    session.add(
        Participant(
            id=DEMO_PARTICIPANT_ID,
            participant_code=DEMO_PARTICIPANT_CODE,
            enrollment_date=start,
            status="active",
            onboarding_completed_at=start,
        )
    )
    session.add(
        ParticipantProfile(
            participant_id=DEMO_PARTICIPANT_ID,
            chronotype_category=persona.chronotype_label,
            # The one trait the pipeline requires (app.pipeline.traits).
            # Drawn from the source-backed chronotype distribution by the
            # seeded generator -- see demo_generator.draw_persona.
            intrinsic_dlmo_time=hour_to_clock_time(persona.intrinsic_dlmo_hour),
            # adapted/current state are deliberately left empty: the
            # state engine initialises them itself on the first run.
            synthetic_personality_profile={
                "demo_dataset": DEMO_MARKER,
                "synthetic": True,
                "label": DEMO_LABEL,
                "description": DEMO_DESCRIPTION,
                "data_source": "Deterministic synthetic generator (scripts/demo/demo_generator.py)",
                "generator_version": GENERATOR_VERSION,
                "seed": seed,
                "dataset_checksum": checksum,
            },
        )
    )
    session.flush()
    return "created"


def upsert_observations(session, days: list[GeneratedDay]) -> dict:
    from app.api.repositories.behavior_repository import BehaviorRepository

    repo = BehaviorRepository(session)
    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    for d in days:
        obs_date = date_cls.fromisoformat(d.observation_date)
        fields = _row_fields(d)
        existing = repo.get_for_date(DEMO_PARTICIPANT_ID, obs_date)
        if existing is None:
            counts["inserted"] += 1
        elif all(getattr(existing, k) == v for k, v in fields.items()):
            counts["unchanged"] += 1
            continue
        else:
            counts["updated"] += 1
        repo.upsert(DEMO_PARTICIPANT_ID, obs_date, **fields)
    return counts


def pipeline_owned_label_dates(session) -> set:
    from sqlalchemy import select

    from app.database.models import CircadianLabel

    rows = session.execute(
        select(CircadianLabel.target_date, CircadianLabel.prediction_status).where(
            CircadianLabel.participant_id == DEMO_PARTICIPANT_ID, CircadianLabel.is_latest.is_(True)
        )
    ).all()
    return {r.target_date for r in rows if (r.prediction_status or "").lower() in {"success", "insufficient_history", "no_prediction"}}


def run_chronological_inference(session_factory, start: date_cls) -> list[dict]:
    """Days 7..30, strictly in order, through the production inference path."""

    from sqlalchemy import select

    from app.api.errors import ApplicationError
    from app.api.repositories.circadian_repository import CircadianRepository
    from app.api.repositories.intervention_repository import InterventionRepository
    from app.api.repositories.participant_repository import ParticipantRepository
    from app.api.repositories.safety_repository import SafetyRepository
    from app.api.services.inference_service import InferenceService
    from app.api.services.status_service import StatusService
    from app.database.models import DailyObservation, InterventionLog, Recommendation
    from app.effectiveness.backfill import backfill_compliance
    from app.personalization.update import update_personalization_state
    from app.safety.engine import SafetyEngine

    check = session_factory()
    done = pipeline_owned_label_dates(check)
    check.close()

    # Chronology guard: processed days must be a contiguous prefix of days 7..30.
    targets = [start + timedelta(days=d - 1) for d in range(FIRST_PREDICTION_DAY, NUM_DAYS + 1)]
    seen_gap = False
    for t in targets:
        if t not in done:
            seen_gap = True
        elif seen_gap:
            raise DemoSeedError(
                f"Existing DEMO-001 results are out of chronological order ({t} processed after an unprocessed earlier day). "
                "The state engine only ever moves forward; rebuild with --reset."
            )

    log: list[dict] = []
    for day_number, target in zip(range(FIRST_PREDICTION_DAY, NUM_DAYS + 1), targets):
        session = session_factory()
        try:
            status_service = StatusService(
                ParticipantRepository(session), CircadianRepository(session), InterventionRepository(session), SafetyRepository(session)
            )
            service = InferenceService(session_factory, session, status_service, SafetyEngine())
            try:
                response = service.run(DEMO_PARTICIPANT_ID, target, force_rerun=False)
            except ApplicationError as exc:
                log.append({"day": day_number, "date": str(target), "status": "FAILED", "detail": f"{exc.message} ({exc.detail})"})
                print(f"  day {day_number:2d} {target}: FAILED -- {exc.message} ({exc.detail}). Stopping: later days depend on this state.")
                break

            entry = {
                "day": day_number,
                "date": str(target),
                "status": response.pipeline_status,
                "reused_existing": response.idempotent_short_circuit,
                "compliance_backfilled": False,
                "personalization": None,
            }

            if not response.idempotent_short_circuit:
                # Same post-inference steps as app/scripts/run_30day_demo.py.
                log_row = session.execute(
                    select(InterventionLog).where(InterventionLog.participant_id == DEMO_PARTICIPANT_ID, InterventionLog.log_date == target)
                ).scalar_one_or_none()
                if log_row is not None:
                    recommendation = session.get(Recommendation, log_row.recommendation_id)
                    observation = session.execute(
                        select(DailyObservation).where(
                            DailyObservation.participant_id == DEMO_PARTICIPANT_ID, DailyObservation.observation_date == target
                        )
                    ).scalar_one_or_none()
                    entry["compliance_backfilled"] = bool(backfill_compliance(log_row, recommendation, observation).applied)
                    session.commit()
                    outcome = update_personalization_state(session, DEMO_PARTICIPANT_ID, recommendation.intervention_type, target + timedelta(days=1))
                    entry["personalization"] = getattr(outcome, "status", None) or str(outcome)[:60]

            log.append(entry)
            print(
                f"  day {day_number:2d} {target}: {entry['status']}"
                f"{' (already processed)' if entry['reused_existing'] else ''}"
                f"{' - compliance backfilled' if entry['compliance_backfilled'] else ''}"
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    return log


def db_counts(session) -> dict:
    from sqlalchemy import func, select

    out = {}
    for table in participant_scoped_tables():
        out[table.name] = session.execute(select(func.count()).select_from(table).where(table.c.participant_id == DEMO_PARTICIPANT_ID)).scalar_one()
    return out


def write_manifest(
    target: dict, seed: int, start: date_cls, checksum: str, counts: dict, inference_log: list, schema: str, after: dict, changed: list
) -> None:
    successful = sum(1 for e in inference_log if e["status"] == "SUCCESS")
    manifest = {
        "participant_code": DEMO_PARTICIPANT_CODE,
        "participant_id": DEMO_PARTICIPANT_ID,
        "label": DEMO_LABEL,
        "description": DEMO_DESCRIPTION,
        "synthetic": True,
        "generator_version": GENERATOR_VERSION,
        "random_seed": seed,
        "start_date": str(start),
        "end_date": str(start + timedelta(days=NUM_DAYS - 1)),
        "first_prediction_day": FIRST_PREDICTION_DAY,
        "observation_records": counts.get("daily_observations", 0),
        "inference_days_attempted": len(inference_log),
        "inference_days_success": successful,
        "inference_statuses": {e["date"]: e["status"] for e in inference_log},
        "persisted_records": counts,
        "database_target": {"type": target["type"], "database": target["database"], "schema_revision": schema},
        "dataset_checksum_sha256": checksum,
        "non_demo_data_unchanged_during_seed": not [t for t in changed if t != "training_runs"],
        "shared_tables_changed_during_seed": changed,
        "non_demo_fingerprint_after_seed": {t: v["sha256"] for t, v in after.items()},
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "Reproducibility record only. The database is authoritative; every derived value was produced by the existing CircadianIQ pipeline.",
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- main


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Validate and show the plan; write nothing.")
    parser.add_argument("--reset", action="store_true", help="Delete DEMO-001's rows (only) before seeding.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--start-date", type=date_cls.fromisoformat, default=DEFAULT_START_DATE)
    parser.add_argument("--skip-inference", action="store_true", help="Seed observations only.")
    args = parser.parse_args(argv)

    from app.config.settings import load_config
    from app.database.engine import create_app_engine, create_session_factory
    from app.logging_config import setup_logging

    config = load_config()
    setup_logging("WARNING")
    target = describe_target(config.database_url)
    print(f"Target database: {target['type']} -> {target['database']}  (CIRCADIANIQ_ENV={config.environment})")

    try:
        guard_target(config, target)
        engine = create_app_engine(config)
        schema = guard_schema(engine)
        print(f"Schema revision: {schema} (Alembic head)")

        persona, days = generate(args.seed, args.start_date)
        validate_days(days)
        checksum = dataset_checksum(persona, days)
        end = args.start_date + timedelta(days=NUM_DAYS - 1)
        print(f"Generated {len(days)} validated days {args.start_date} .. {end}  seed={args.seed}  checksum={checksum[:16]}...")
        print(f"Persona: chronotype={persona.chronotype_label} intrinsic DLMO={persona.intrinsic_dlmo_hour:.2f}h (seeded draw)")

        session_factory = create_session_factory(engine)
        session = session_factory()
        try:
            existing = find_demo_participant(session)
            done = pipeline_owned_label_dates(session) if existing else set()
            before = foreign_fingerprint(session)
        finally:
            session.close()
        print(f"DEMO-001 currently: {'present' if existing else 'absent'}; processed days: {len(done)}")

        if args.dry_run:
            print("\nDRY RUN -- nothing will be written. Plan:")
            print(f"  participant  : {'reset, then ' if args.reset and existing else ''}{'verify' if existing and not args.reset else 'create'} "
                  f"{DEMO_PARTICIPANT_CODE} (id {DEMO_PARTICIPANT_ID})")
            print(f"  observations : upsert 30 rows for {args.start_date} .. {end}")
            print(f"  inference    : days {FIRST_PREDICTION_DAY}..{NUM_DAYS} chronologically via InferenceService"
                  f"{' (skipped)' if args.skip_inference else ''}")
            for d in days:
                print(f"    day {d.day:2d} {d.observation_date} {d.period:<10}{' setback' if d.setback else '':8}"
                      f"{' free' if d.is_free_day else '     '} sleep {d.sleep_onset_time}-{d.sleep_offset_time} "
                      f"light {d.morning_light_duration_minutes:>4.0f}m screens-end {d.evening_screen_end_time} meal {d.last_meal_time}")
            return 0

        # --- seed participant + observations: one transaction ---
        session = session_factory()
        try:
            if args.reset and existing is not None:
                deleted = reset_demo(session)
                print(f"Reset DEMO-001 rows: {deleted}")
            participant_state = ensure_participant(session, persona, args.start_date, args.seed, checksum)
            obs_counts = upsert_observations(session, days)
            session.commit()
        except Exception:
            session.rollback()
            print("Seeding failed -- transaction rolled back; nothing was written.")
            raise
        finally:
            session.close()
        print(f"Participant {DEMO_PARTICIPANT_CODE}: {participant_state}; observations {obs_counts}")

        if obs_counts["inserted"] or obs_counts["updated"]:
            s = session_factory()
            already = pipeline_owned_label_dates(s)
            s.close()
            if already:
                raise DemoSeedError("Observations changed but derived results already exist for DEMO-001; rebuild with --reset.")

        inference_log: list = []
        if not args.skip_inference:
            print(f"\nChronological inference, days {FIRST_PREDICTION_DAY}..{NUM_DAYS}:")
            inference_log = run_chronological_inference(session_factory, args.start_date)

        session = session_factory()
        try:
            after = foreign_fingerprint(session)
            counts = db_counts(session)
        finally:
            session.close()

        changed = sorted(t for t in before if before[t] != after.get(t))
        participant_changes = [t for t in changed if t not in {"training_runs"}]
        print("\nPersisted DEMO-001 rows:", json.dumps(counts))
        if participant_changes:
            print(f"WARNING: rows outside DEMO-001 changed in: {participant_changes}")
        else:
            print("Non-DEMO-001 data: unchanged in every table" + (" (training_runs: pipeline registered its model run)" if "training_runs" in changed else "") + ".")

        write_manifest(target, args.seed, args.start_date, checksum, counts, inference_log, schema, after, changed)
        print(f"Manifest: {MANIFEST_PATH.relative_to(PROJECT_ROOT)}")
        print("Next: python scripts/demo/verify_demo_participant.py")
        engine.dispose()
        return 1 if participant_changes else 0
    except DemoSeedError as exc:
        print(f"REFUSED: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
