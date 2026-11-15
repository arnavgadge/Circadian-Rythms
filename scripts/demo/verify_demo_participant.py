"""Verify the DEMO-001 demonstration directly against the configured database
and through the real FastAPI application.

    python scripts/demo/verify_demo_participant.py

Read-only. Every check below is an actual SQL query or an actual HTTP
request to ``app.api.main.create_app()`` (in-process ``TestClient``,
same configured database) -- nothing is inferred from the frontend.
Prints a PASS/FAIL line per check, writes
``scripts/demo/demo_verification.json``, and exits non-zero if any
check fails.
"""

from __future__ import annotations

import json
import sys
from datetime import date as date_cls, datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, DEMO_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from seed_demo_participant import (  # noqa: E402
    DEMO_MARKER,
    DEMO_PARTICIPANT_CODE,
    DEMO_PARTICIPANT_ID,
    FIRST_PREDICTION_DAY,
    MANIFEST_PATH,
    NUM_DAYS,
    describe_target,
    foreign_fingerprint,
)

REPORT_PATH = DEMO_DIR / "demo_verification.json"


def _hhmm(t) -> str | None:
    return t.strftime("%H:%M") if t is not None else None


def _circ_minutes(a, b) -> float:
    da = a.hour * 60 + a.minute
    db = b.hour * 60 + b.minute
    d = (da - db) % 1440
    return d - 1440 if d > 720 else d


def main() -> int:
    import logging
    import os

    os.environ.setdefault("CIRCADIANIQ_LOG_LEVEL", "WARNING")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    from fastapi.testclient import TestClient
    from sqlalchemy import func, select

    from app.api.main import create_app
    from app.api.schemas.daily_entry import DailyEntryRequest
    from app.config.settings import load_config
    from app.database.engine import create_app_engine, create_session_factory
    from app.database.models import (
        AlignmentResult,
        CircadianLabel,
        ContributorResult,
        DailyObservation,
        InterventionLog,
        Participant,
        ParticipantProfile,
    )
    from app.fusion.config import DEFAULT_FUSION_CONFIG
    from app.logging_config import setup_logging
    from app.state.config import DEFAULT_STATE_ENGINE_CONFIG

    setup_logging("WARNING")
    config = load_config()
    target = describe_target(config.database_url)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else {}
    start = date_cls.fromisoformat(manifest["start_date"]) if manifest else None

    checks: list[dict] = []

    def check(name: str, ok: bool, evidence) -> None:
        checks.append({"check": name, "result": "PASS" if ok else "FAIL", "evidence": evidence})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}\n       {evidence}")

    print(f"Database: {target['type']} -> {target['database']}\n")
    engine = create_app_engine(config)
    s = create_session_factory(engine)()
    pid = DEMO_PARTICIPANT_ID

    # 1. exactly one demonstration participant
    demo_rows = s.execute(select(Participant.id, Participant.participant_code).where(Participant.participant_code == DEMO_PARTICIPANT_CODE)).all()
    profile = s.get(ParticipantProfile, pid)
    marker = (profile.synthetic_personality_profile or {}).get("demo_dataset") if profile else None
    check(
        "1. Exactly one DEMO-001 participant, marked synthetic",
        len(demo_rows) == 1 and demo_rows[0].id == pid and marker == DEMO_MARKER,
        f"SELECT id, participant_code FROM participants WHERE participant_code='DEMO-001' -> {[tuple(r) for r in demo_rows]}; marker={marker!r}",
    )

    # 2-5. 30 consecutive, unique, owned dates
    obs = s.execute(select(DailyObservation).where(DailyObservation.participant_id == pid).order_by(DailyObservation.observation_date)).scalars().all()
    dates = [o.observation_date for o in obs]
    expected = [start + timedelta(days=i) for i in range(NUM_DAYS)] if start else []
    check("2. Exactly 30 daily observation dates", len(dates) == NUM_DAYS, f"COUNT(daily_observations WHERE participant_id={pid}) = {len(dates)}; range {dates[0] if dates else None} .. {dates[-1] if dates else None}")
    check("3. All observation rows belong to DEMO-001", all(o.participant_id == pid for o in obs), f"distinct participant_id over those rows = {sorted({o.participant_id for o in obs})}")
    check("4. Dates are consecutive and match the manifest", dates == expected, f"manifest {manifest.get('start_date')} .. {manifest.get('end_date')}; gaps = {[str(b) for a, b in zip(dates, dates[1:]) if (b - a).days != 1]}")
    dupes = s.execute(
        select(DailyObservation.observation_date, func.count()).where(DailyObservation.participant_id == pid).group_by(DailyObservation.observation_date).having(func.count() > 1)
    ).all()
    check("5. No duplicate participant/date observations", not dupes, f"GROUP BY observation_date HAVING COUNT(*)>1 -> {dupes}")

    # 6. validation constraints
    invalid = []
    for o in obs:
        try:
            DailyEntryRequest(
                observation_date=o.observation_date,
                sleep_onset_time=_hhmm(o.sleep_onset_time),
                sleep_offset_time=_hhmm(o.sleep_offset_time),
                morning_light_start_time=_hhmm(o.morning_light_start_time),
                morning_light_duration_minutes=o.morning_light_duration_minutes,
                evening_screen_end_time=_hhmm(o.evening_screen_end_time),
                evening_screen_duration_minutes=o.evening_screen_duration_minutes,
                last_meal_time=_hhmm(o.last_meal_time),
                exercise_time=_hhmm(o.exercise_time),
                last_caffeine_time=_hhmm(o.last_caffeine_time),
                caffeine_amount_mg=o.caffeine_amount_mg,
                is_free_day=o.is_free_day,
            )
        except Exception as exc:  # noqa: BLE001
            invalid.append(f"{o.observation_date}: {exc}")
    required_null = [str(o.observation_date) for o in obs if None in (o.sleep_onset_time, o.sleep_offset_time, o.morning_light_duration_minutes, o.evening_screen_duration_minutes, o.last_meal_time, o.exercise_time, o.last_caffeine_time, o.caffeine_amount_mg)]
    check("6. Every observation passes the API's DailyEntryRequest validation; no core field missing", not invalid and not required_null, f"invalid={invalid or 'none'}; rows missing a core field={required_null or 'none'}")

    # 7-9. labels
    labels = s.execute(select(CircadianLabel).where(CircadianLabel.participant_id == pid).order_by(CircadianLabel.target_date)).scalars().all()
    latest = [lb for lb in labels if lb.is_latest]
    warmup_end = start + timedelta(days=FIRST_PREDICTION_DAY - 2) if start else None
    warmup_labels = [lb for lb in labels if warmup_end and lb.target_date <= warmup_end]
    check("8. Days 1-6 have no daily prediction rows", not warmup_labels, f"COUNT(circadian_labels WHERE target_date <= {warmup_end}) = {len(warmup_labels)}")

    pred_dates = [start + timedelta(days=d - 1) for d in range(FIRST_PREDICTION_DAY, NUM_DAYS + 1)] if start else []
    latest_by_date = {lb.target_date: lb for lb in latest}
    statuses = {str(d): (latest_by_date[d].prediction_status if d in latest_by_date else None) for d in pred_dates}
    per_date = s.execute(
        select(CircadianLabel.target_date, func.count()).where(CircadianLabel.participant_id == pid, CircadianLabel.is_latest.is_(True)).group_by(CircadianLabel.target_date).having(func.count() > 1)
    ).all()
    aligns = s.execute(select(func.count()).select_from(AlignmentResult).where(AlignmentResult.participant_id == pid)).scalar_one()
    contribs = s.execute(select(func.count()).select_from(ContributorResult).where(ContributorResult.participant_id == pid)).scalar_one()
    logs = s.execute(select(func.count()).select_from(InterventionLog).where(InterventionLog.participant_id == pid)).scalar_one()
    complete = all(latest_by_date.get(d) and latest_by_date[d].fused_dlmo_time and latest_by_date[d].xgboost_dlmo_time and latest_by_date[d].state_model_dlmo_time for d in pred_dates)
    check(
        "9. Days 7-30 have persisted results (one is_latest label each, with XGBoost, state and fused DLMO)",
        len(pred_dates) == 24 and all(v == "success" for v in statuses.values()) and not per_date and complete,
        f"statuses={sorted(set(statuses.values()))} over {len(statuses)} dates; duplicate is_latest={per_date}; alignment_results={aligns}, contributor_results={contribs}, intervention_log={logs}",
    )

    # 7. chronological processing
    computed = [latest_by_date[d].computed_at for d in pred_dates if d in latest_by_date]
    check("7. Inference was processed chronologically", computed == sorted(computed) and len(computed) == 24, f"circadian_labels.computed_at strictly follows target_date order: first {computed[0] if computed else None}, last {computed[-1] if computed else None}")

    # 10. state progression
    # The orchestrator writes each day's FUSED estimate back as the
    # participant's current state, so the state engine's step for day N
    # starts from fused(N-1): its continuity cap bounds state(N) - fused(N-1).
    state_cap = DEFAULT_STATE_ENGINE_CONFIG.daily_continuity_cap_minutes
    state_steps = [abs(_circ_minutes(latest_by_date[b].state_model_dlmo_time, latest_by_date[a].fused_dlmo_time)) for a, b in zip(pred_dates, pred_dates[1:])]
    fused_viol = []
    for a, b in zip(pred_dates, pred_dates[1:]):
        lb = latest_by_date[b]
        cap = DEFAULT_FUSION_CONFIG.continuity_cap_minutes_by_regime.get(next((r for r in DEFAULT_FUSION_CONFIG.continuity_cap_minutes_by_regime if str(r.value) == lb.disagreement_regime), None), DEFAULT_FUSION_CONFIG.default_continuity_cap_minutes)
        step = abs(_circ_minutes(lb.fused_dlmo_time, latest_by_date[a].fused_dlmo_time))
        if step > cap + 0.5:
            fused_viol.append(f"{b}: {step:.0f}>{cap:.0f}")
    last = latest_by_date.get(pred_dates[-1]) if pred_dates else None
    profile_ok = profile is not None and last is not None and profile.current_dlmo_date == last.target_date and _hhmm(profile.current_dlmo_time) == _hhmm(last.fused_dlmo_time)
    check(
        "10. Historical state progression is intact",
        profile_ok and max(state_steps or [0]) <= state_cap + 0.5 and not fused_viol,
        f"profile current state = {_hhmm(profile.current_dlmo_time) if profile else None} on {profile.current_dlmo_date if profile else None} (== day-30 fused {_hhmm(last.fused_dlmo_time) if last else None}); "
        f"max |state(N) - fused(N-1)| = {max(state_steps or [0]):.0f} min (state-engine cap {state_cap:.0f}); fused continuity-cap violations: {fused_viol or 'none'}; "
        f"intrinsic {_hhmm(profile.intrinsic_dlmo_time) if profile else None}, adapted (latest only) {_hhmm(profile.adapted_dlmo_time) if profile else None}",
    )

    # 11. API retrieval
    api_problems = []
    with TestClient(create_app()) as client:
        r = client.get(f"/api/v1/participants/{pid}")
        if r.status_code != 200 or r.json().get("participant_code") != DEMO_PARTICIPANT_CODE:
            api_problems.append(f"GET participant -> {r.status_code}")
        hist = client.get(f"/api/v1/participants/{pid}/circadian/history", params={"start_date": str(dates[0]), "end_date": str(dates[-1]), "limit": 30}).json()
        beh = client.get(f"/api/v1/participants/{pid}/behavior", params={"start_date": str(dates[0]), "end_date": str(dates[-1]), "limit": 30}).json()
        ivs = client.get(f"/api/v1/participants/{pid}/interventions", params={"limit": 60}).json()
        if hist.get("count") != 24:
            api_problems.append(f"history count {hist.get('count')}")
        if beh.get("count") != 30:
            api_problems.append(f"behavior count {beh.get('count')}")
        if ivs.get("count") != logs:
            api_problems.append(f"interventions count {ivs.get('count')} != {logs}")
        mismatches = 0
        for d in pred_dates:
            st = client.get(f"/api/v1/participants/{pid}/status", params={"target_date": str(d)}).json()
            if st.get("biological_clock") != _hhmm(latest_by_date[d].fused_dlmo_time) or not st.get("prediction_available"):
                mismatches += 1
        for d in expected[: FIRST_PREDICTION_DAY - 1]:
            st = client.get(f"/api/v1/participants/{pid}/status", params={"target_date": str(d)}).json()
            if st.get("prediction_available"):
                api_problems.append(f"warm-up {d} reports a prediction")
        if mismatches:
            api_problems.append(f"{mismatches} status/DB clock mismatches")
    check(
        "11. All results retrievable through the existing API (status per date, history, behavior, interventions)",
        not api_problems,
        f"GET /status for 24 prediction dates matched DB fused DLMO; warm-up dates report no prediction; history=24, behavior=30, interventions={logs}; problems={api_problems or 'none'}",
    )

    # 12. non-demo data untouched
    current = foreign_fingerprint(s)
    baseline = manifest.get("non_demo_fingerprint_after_seed", {})
    drift = sorted(t for t, v in current.items() if baseline.get(t) and baseline[t] != v["sha256"])
    real_rows = {t: v["rows"] for t, v in current.items() if t in ("participants", "daily_observations", "circadian_labels")}
    check(
        "12. Existing (non-DEMO-001) data was not modified",
        bool(manifest.get("non_demo_data_unchanged_during_seed")) and not drift,
        f"seed run before/after fingerprint equal: {manifest.get('non_demo_data_unchanged_during_seed')} (shared tables written by the pipeline: {manifest.get('shared_tables_changed_during_seed')}); "
        f"changed since seeding: {drift or 'none'}; non-demo row counts now {real_rows}",
    )

    s.close()
    engine.dispose()

    failed = [c for c in checks if c["result"] == "FAIL"]
    REPORT_PATH.write_text(
        json.dumps(
            {
                "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "database": {"type": target["type"], "database": target["database"]},
                "participant": DEMO_PARTICIPANT_CODE,
                "passed": len(checks) - len(failed),
                "failed": len(failed),
                "checks": checks,
            },
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed. Report: {REPORT_PATH.relative_to(PROJECT_ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
