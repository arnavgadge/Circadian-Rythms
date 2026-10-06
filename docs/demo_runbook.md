# CircadianIQ Demo Runbook

**Release:** v1.0.0-research-demo
**Phase 17 final audit status:** CONDITIONAL PASS
**Audience:** a live audience (e.g. a professor or reviewer), 5-10 minutes.

This is a step-by-step script for demonstrating CircadianIQ live. Every
step below references a specific, real, deterministic demo participant
ID or a specific file/query -- nothing in this walkthrough depends on
random or non-deterministic behavior. The four demo participants
(`1`, `3`, `25`, `41`) are seeded once, ahead of time, into a dedicated
database (`data/demo.db`) that is never the developer's real working
database (`data/circadianiq.db`).

---

## Setup (do this before the audience arrives)

The demo participants already exist in `data/demo.db`. If you need to
(re-)seed them, run (from the repository root, with the virtualenv
activated):

```
python -m app.scripts.seed_demo_scenarios
```

This is deterministic given `generation_seed=777` and is safe to
re-run. See `release/demo/demo_scenarios.json` for the exact
per-scenario disclosure this script writes.

Start two terminals:

```
# Terminal 1 -- API pointed at the demo database
set CIRCADIANIQ_DATABASE_URL=sqlite:///data/demo.db   # Windows cmd; for PowerShell use: $env:CIRCADIANIQ_DATABASE_URL="sqlite:///data/demo.db"
uvicorn app.api.main:app --reload
```

```
# Terminal 2 -- frontend
cd frontend
npm run dev
```

- Frontend dev URL: **http://127.0.0.1:5173** (dashboard at
  `/dashboard/{participant_id}`, onboarding at `/onboarding`, daily log
  at `/log/{participant_id}`).
- API base: **http://127.0.0.1:8000/api/v1** (interactive docs at
  **http://127.0.0.1:8000/docs**).
- The frontend's `VITE_API_BASE_URL` (see `frontend/.env.example`)
  already defaults to `http://127.0.0.1:8000/api/v1`, so no frontend
  config change is needed as long as the API is running on its default
  port.

**Before going live**, sanity-check that the API is actually reading
the demo database by hitting
`GET http://127.0.0.1:8000/api/v1/participants/1/status` and confirming
it returns participant 1's NORMAL-scenario data (confidence label
`high`, no active safety flag). This was confirmed working end-to-end
at authoring time.

If you would rather reproduce the entire release (data generation,
training, all diagnostics, and this demo seeding) as one command instead
of walking each phase by hand, `python -m app.scripts.reproduce_release`
does that against a disposable database and never touches
`data/demo.db` or the real developer database. It is not the focus of
this runbook -- it is mentioned here only as an alternative entry point,
and it is also the source of the validated metrics cited in step 14
below.

---

## 1. Introduce the problem

CircadianIQ computationally estimates a person's circadian phase
(DLMO) from everyday behavioral signals -- sleep, light, screens,
meals, exercise -- and scores how well their actual routine aligns
with that estimate. It is **not** a clinical or diagnostic device, and
every number in this demo is produced by a synthetic-data research
system: nothing here has been validated against a real human circadian
measurement.

## 2. Show onboarding

Since participants 1, 3, 25, and 41 already have weeks of seeded
history, use a **fresh** participant to demonstrate the onboarding UX
itself.

- Open **http://127.0.0.1:5173/onboarding**.
- Walk through the flow: welcome -> scientific-boundary acknowledgment
  -> a morning/evening-preference slider -> a free-day sleep-midpoint
  time field -> a participant code (e.g. `DEMO-NEWCOMER`).
- Say explicitly: this is a new participant created only to show the
  onboarding UX -- it is not one of the four demo scenarios.
- Point out that the form deliberately collects only what the real
  `POST /participants` endpoint accepts: `participant_code`,
  `meq_score`, and `msfsc_time` (confirmed against
  `frontend/src/pages/Onboarding.tsx` and `docs/api_architecture.md`).
  There is no full item-level MEQ/MCTQ questionnaire -- that is a
  documented, deliberate scope limit, not an oversight.
- After "Finish," the flow routes to that new participant's daily-log
  page (`/log/{id}`) -- note that a brand-new participant has no
  prediction yet, since inference needs behavioral history first. Then
  switch back to the seeded participants for the rest of the demo.

## 3. Show behavioral history

- Go to **http://127.0.0.1:5173/log/1** (or `/log/25`).
- This is the daily behavioral data-entry / log view backed by
  `POST /participants/{id}/behavior`. Point out the categories it
  covers: sleep, morning light, evening screen time, meals, exercise --
  the same six-day behavioral window the ML model consumes (Phase 4
  feature engineering), and explicitly **not** any physiological signal
  (heart rate, HRV, wrist temperature are structurally kept in a
  separate table, `physiology_logs`, never read by Version-1 ML).

## 4. Run inference

- Go to **http://127.0.0.1:5173/dashboard/1**.
- Click the button labeled **"Update today's estimate"** (top-right of
  the dashboard grid -- confirmed verbatim from
  `frontend/src/pages/Dashboard.tsx`).
- This calls `POST /api/v1/participants/1/inference`, which runs the
  full pipeline (features -> XGBoost -> state engine -> fusion ->
  alignment -> contributors -> recommendation -> safety) and writes an
  atomic result back to SQL. Note it is idempotent: re-running it for a
  date already computed returns the existing result rather than
  duplicating it.

## 5. Show the biological clock

- Point to the circular clock visualization at the top of the
  dashboard (`BiologicalClockCard`). It plots the estimated DLMO, the
  "ideal" sleep onset derived from it, and the participant's actual
  sleep onset on one midnight-safe circular face -- explain that this
  is a computational estimate from behavior, not a lab measurement.

## 6. Show alignment

- Point to the alignment score card and its 5-component breakdown
  (sleep consistency 25%, morning light 25%, evening screen 20%, meal
  timing 15%, social jetlag 15%), combined as
  `0.60 * phase_alignment + 0.40 * behavioral_alignment` into one 0-100
  score.

## 7. Show contributors

- Point to the top-contributors list. Explain it identifies (at most)
  the top 3 of 5 candidate behavioral signals driving the participant's
  current misalignment, each labeled with a direction
  (`hurting` / `opportunity_missed` / `neutral`) and explicitly
  non-causal language -- "modeled influence," never "cause."

## 8. Show the recommendation

- Point to the recommendation card: exactly one primary intervention
  plus up to two supporting nudges, sourced only from the
  `recommendations` database catalogue (never free-form or
  LLM-generated text).

## 9. Show progress/history

- Scroll to the **Progress** section (`TrajectoryChart`). Switch the
  time-range buttons between **7 days / 30 days / 90 days**, and switch
  the metric tabs between "Estimated biological clock," "Alignment
  score," and "Confidence." Point out that the clock-time series is
  rendered *unwrapped* so a midnight-crossing trend (e.g. 23:50 ->
  00:10) draws as one continuous line instead of a misleading vertical
  jump.

## 10. Demonstrate intervention feedback (Phase 12 effectiveness)

- Point to the **Intervention progress** card (`InterventionProgress`).
  It shows, for the participant's most recently recommended
  intervention type, a compliant-days-out-of-observed-days count, and
  -- once enough history exists -- a labeled effect estimate at one of
  three escalating evidence tiers: "Observed change" (before/after),
  "Change compared with a similar previous period" (matched), or
  "Estimated personal effect" (personal regression). Read the causal
  caveat text shown beneath it aloud: this is an association, not a
  proven causal effect.

## 11. Demonstrate personalization conceptually

- The demo database does **not** include a participant who has reached
  the most mature personalization stage (`PERSONALIZATION_MATURE`).
  Say this plainly to the audience: it is not available to show live in
  this demo.
- Reaching it requires roughly 12 weeks (42+ observations) of real
  intervention-logging and compliance-outcome cycles through the
  recommendation engine for a single participant/intervention-type pair
  -- materially more setup than the four seeded scenarios, and
  documented as an optional future addition rather than silently
  omitted (see `release/demo/demo_scenarios.json`,
  `personalization_mature_scenario`).
- Explain the progression conceptually instead: each
  (participant, intervention type) pair independently graduates through
  four phases as evidence accumulates --
  `literature -> personal_ranking -> personal_effect -> adaptive_policy`.
  Early on, recommendations lean on literature-style defaults; as
  compliance and outcome history accumulate for that specific person,
  the system blends in (and eventually replaces literature with) a
  personal effect model, and ultimately a contextual bandit
  (Thompson sampling) that adapts intervention selection to that
  person's own observed responses -- always falling back to the
  literature default if the personal model fails a validity check.

## 12. Demonstrate the safety boundary

**Participant 25 (MODERATE):**

- Go to **http://127.0.0.1:5173/dashboard/25**.
- Point to the safety banner: a calm **"Pattern note"** is shown
  alongside the recommendation, which is still fully displayed. Say
  aloud: "This participant has a MODERATE safety flag -- the system
  surfaces a pattern note, but the recommendation is not withheld."
  You can also confirm the underlying flag row with query 5 in
  `docs/dbms_demo_queries.sql` (`severity = 'MODERATE'`,
  `recommendation_suppressed = 0`).

**Participant 41 (HIGH):**

- Go to **http://127.0.0.1:5173/dashboard/41**.
- Point to the safety banner and the recommendation area: the
  recommendation is suppressed entirely (not dimmed, not
  partially shown -- absent). Say aloud: "This participant has a HIGH
  safety flag -- the recommendation is withheld entirely, by design."
- Disclose honestly, in the presenter's own words, what
  `release/demo/demo_scenarios.json` states about this participant:
  its underlying DLMO trajectory was a `constructed_pathological_trajectory`
  -- deliberately, directly authored rather than emergent from
  realistic behavioral inputs -- specifically so this HIGH-severity
  safety boundary could be demonstrated at all. This is the one demo
  participant whose data was constructed rather than naturally
  generated, and that is disclosed here rather than left implicit.

## 13. Show DBMS architecture

- Open a third terminal (or pause the frontend) and run the reference
  query file against the demo database directly:

  ```
  sqlite3 data/demo.db < docs/dbms_demo_queries.sql
  ```

  For a live audience, it usually reads better to run it interactively
  instead, pasting one query at a time:

  ```
  sqlite3 data/demo.db
  ```

- Suggested queries to run live from `docs/dbms_demo_queries.sql`:
  - **Query 2** -- shows the `is_latest` event-sourcing pattern on
    `circadian_labels` for participant 1 (total rows ever written vs.
    the single currently-authoritative row per date).
  - **Query 5** -- shows `safety_flags` for participants 25 and 41 side
    by side, including `severity` and `recommendation_suppressed`,
    which is exactly what step 12 just showed in the UI, now confirmed
    directly in SQL.
- Mention the schema is 14 core tables plus one Phase-12 addition
  (`intervention_effect_estimates`), documented fully in
  `docs/final_database_design.md`, with SQLite used for this demo and
  PostgreSQL supported by the same code via one environment variable.

## 14. Show ML validation results

- Open `release/results/model_metrics.csv` and 1-2 figures under
  `release/figures/`, e.g. `01_actual_vs_predicted_circular.png` and
  `02_absolute_error_distribution.png`.
- State the headline result using this exact wording, every time:
  **"93.73% of held-out synthetic test windows were within ±60
  minutes."** Never say "93.73% accurate on humans" or anything that
  implies real-human or clinical validation.
- Full context to share alongside it: held-out synthetic test set MAE
  24.47 min, RMSE 31.86 min, median absolute error 19.71 min, bias
  -0.82 min. Cross-validation: MAE 25.22 ± 1.20 min, 93.03% ± 0.74%
  within ±60 min. Two non-learned baselines for comparison:
  participant-mean (MAE 57.2 min, 67.6% within ±60 min) and
  MSFsc-proxy (MAE 342.1 min, 0.0% within ±60 min) -- CircadianIQ's
  model outperforms both by a wide margin, on synthetic data.
- State the caveat explicitly, every time these numbers are shown:
  **this system has never been validated against real human DLMO
  measurements.** These figures describe performance on held-out
  synthetic test windows only.
- If asked "how was this produced end to end," mention
  `python -m app.scripts.reproduce_release` as the one-command
  reproduction of the full pipeline that generated these exact numbers
  (you do not need to re-run it live; it takes longer than the demo
  window).

---

## Closing note

Everything shown in this demo runs on **synthetic data only**. No
CircadianIQ component has been validated against real human
circadian/DLMO measurements, and the system is **not a clinical
device**. Phase 17's final system-wide audit verdict was **CONDITIONAL
PASS** -- every pass-blocking criterion (no participant/temporal data
leakage, no critical safety failure, sound database transactions,
correct circular-time arithmetic, reproducibility, a working API/UI
contract) was met, conditional only on three documented, non-critical
limitations (see `docs/system_validation_and_audit.md`), none of which
caused an observed incorrect output during that audit. This status is
never relabeled as a plain "PASS" in this or any other release
document.
