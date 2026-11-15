# DEMO-001 — 30-day database-backed research demonstration

One synthetic participant, **DEMO-001** (`participants.id = 9101`), stored in the
**configured** CircadianIQ database and processed day by day by the existing pipeline.
The input behavior is synthetic; every derived value (DLMO estimates, confidence,
alignment, contributors, recommendations, compliance, effect estimates) is a real,
unmodified pipeline output.

## Commands

```bash
# 0. (once, only if needed) bring a stale recommendation catalogue up to date
python scripts/demo/refresh_recommendation_catalogue.py            # show the diff
python scripts/demo/refresh_recommendation_catalogue.py --apply    # back up DB file, update 6 rows in place

# 1. seed + process
python scripts/demo/seed_demo_participant.py --dry-run             # plan only, writes nothing
python scripts/demo/seed_demo_participant.py                       # idempotent; safe to re-run
python scripts/demo/seed_demo_participant.py --reset               # delete DEMO-001's rows only, rebuild

# 2. verify against the database and the real API
python scripts/demo/verify_demo_participant.py                     # 12 checks -> demo_verification.json
```

Then open the frontend at `/demo` (sidebar: **30-Day Research Demo**, or the link on the
entry screen). The frontend locates the participant by `VITE_DEMO_PARTICIPANT_ID`
(default `9101`) and refuses to show anything unless that record's `participant_code`
is `DEMO-001`.

## Files

| File | Purpose |
|---|---|
| `demo_generator.py` | Deterministic 30-day raw-behavior generator (seed `20261005`, start `2026-10-05`). No derived values. |
| `seed_demo_participant.py` | Guards, validation, participant + observation upsert, chronological inference, manifest. |
| `refresh_recommendation_catalogue.py` | Updates stale catalogue rows in place from `app/database/seed.py`. |
| `verify_demo_participant.py` | Database + API verification report. |
| `demo_manifest.json` | Reproducibility record (seed, dates, counts, checksums, non-demo fingerprint). |
| `demo_verification.json` | Latest verification result. |

## Where the data lives (existing schema, no new tables)

```
participants (id 9101, code DEMO-001)
 └─ participant_profiles        chronotype, intrinsic DLMO (seeded draw), latest adapted/current state,
 │                              synthetic_personality_profile = demo marker + seed + dataset checksum
 ├─ daily_observations ×30      RAW behavior only (sleep, light, screens, meals, exercise, caffeine)
 ├─ circadian_labels ×24        DERIVED per day 7..30: XGBoost, state-engine and fused DLMO, disagreement,
 │   │                          confidence, safety status
 │   └─ alignment_results ×24   final / phase / behavioral + 5 components, ideal & actual onset
 │       └─ contributor_results ×72   top-3 ranking per day
 ├─ intervention_log ×24 ──► recommendations (catalogue)   primary recommendation per day, target,
 │                                                          compliance (backfilled from that day's behavior)
 ├─ intervention_effect_estimates ×24   Phase-12 observational estimates (immutable rows)
 ├─ personal_effect_models ×1           personalization phase for the screen intervention
 └─ safety_flags                        none raised for this journey
training_runs (shared)                  the pipeline registers the model run it used
```

Processing order per target day (strictly chronological, days 7 → 30):
`InferenceService.run` (= `POST /participants/{id}/inference`: pipeline → safety engine) →
`backfill_compliance` → `update_personalization_state(as_of = day + 1)` — the same
post-inference steps as `app/scripts/run_30day_demo.py`.

## Known limitations (no backend change made)

* The history/status API returns only the **fused** DLMO; the per-day XGBoost and
  state-engine values are stored in `circadian_labels` but not exposed. Minimum change:
  add `xgboost_dlmo` / `state_model_dlmo` / `disagreement_minutes` to
  `CircadianHistoryEntry` (`app/api/schemas/history.py`) and map them in
  `HistoryService.get_history`.
* The **adapted** state is stored only as the latest value (`participant_profiles`), not
  per day. Minimum change: a nullable `adapted_dlmo_time` column on `circadian_labels`
  (migration) written by `write_circadian_label`.
* The behavior API omits wake time, light start, screen end, caffeine and exercise
  duration (all stored). Minimum change: add them to `BehaviorEntry` + `BehaviorService`.
* Supporting nudges are not persisted per day (schema logs only the primary).
