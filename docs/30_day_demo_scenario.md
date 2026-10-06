# The 30-Day Demo Scenario

A single deterministic, hand-designed 30-day behavioral journey for one
demonstration participant, built on top of the frozen `v1.0.0-research-demo`
CircadianIQ system. **This does not modify any frozen release artifact**
(model, metrics, feature manifest, configs, Phase 17 audit results) --
it is a separate database and a separate narrative fixture layered on
top of the existing, unmodified pipeline.

## 1. Participant persona

**Arjun -- CircadianIQ Demo User**, `participant_id = 9001`,
`participant_code = "DEMO-9001-ARJUN"`, chronotype **Late**, persona:
a screen-heavy user with a mild social-jetlag pattern. This is a
**deliberately designed persona, not a sampled population
participant** -- it was never passed through `app.synthetic`'s
population generator, has no assigned `personality_key` from
`app.synthetic.personalities`, and must never be cited as evidence
about population prevalence or real physiology (see `README.md`
"Scientific boundary"). Its only purpose is a clear, reproducible demo
narrative.

## 2. Why the scenario is deterministic

Every one of the 30 days' behavioral values comes from a plain
arithmetic formula tied to the day index and the five narrative
stages, written in `demo/scenarios/_author_late_screen_recovery_30d.py`
(a one-time **authoring** tool, not part of the runtime pipeline) and
committed as the fixed, human-readable
`demo/scenarios/late_screen_recovery_30d.yaml`. There is no `random`,
`numpy.random`, or seeded-RNG call anywhere in the authoring script or
the seeding script (`app.scripts.seed_30day_demo`, which only reads
the YAML). Small day-to-day variation (e.g. baseline sleep onset
alternating by +/-7.5 minutes) is a fixed, named oscillation or a
linear interpolation between explicit anchor points -- never noise.
Running `seed_30day_demo` + `run_30day_demo` twice against a fresh
database produces the same 30 `daily_observations` rows and (subject
to the frozen model artifact's own determinism, already verified in
Phase 17 audit 21) the same pipeline outputs. See
`tests/test_30day_demo.py` for the executable proof.

## 3. The five stages

| Stage | Days | Narrative |
|---|---|---|
| STAGE_1_BASELINE | 1-7 | Consistently misaligned routine: late sleep, heavy evening screens, weak morning light, late last meal, moderate social jetlag. Held stable (small deterministic variation only) so the system has a coherent 6-day window once prediction begins. |
| STAGE_2_IDENTIFY | 8-10 | The pattern continues unchanged; the system now has a full trailing history and issues its first graduated recommendation. |
| STAGE_3_CHANGE | 11-18 | Deliberate, gradual behavioral improvement (screen cutoff, morning light), with partial compliance early and stronger compliance later. |
| STAGE_4_RESPONSE | 19-24 | Continued behavioral improvement; the estimated biological clock and alignment score are left entirely to the real state engine/fusion/alignment layers. |
| STAGE_5_STABLE | 25-30 | Behavior stabilizes at a substantially, but not perfectly, improved routine. |

## 4. Exact behavioral pattern

See `demo/scenarios/late_screen_recovery_30d.yaml` directly -- every
field for every day is there and human-inspectable (sleep onset/offset,
morning light start+duration, evening screen end+duration, last meal,
exercise, caffeine, social jetlag minutes, free-day flag). Headline
values: baseline sleep onset ~1:45-2:00 AM, baseline evening screen
until ~1:15-1:30 AM (duration >=3h, deliberately in the tier system's
worst "very_high" bucket), baseline morning light <10 minutes
(deliberately in the "none" tier); by the stable period (days 25-30),
screen cutoff has moved to ~12:33-12:45 AM, morning light duration is
35-38 minutes (the "high" tier), and last meal has moved from
~10:45 PM to ~9:50-10:00 PM.

## 5. Intervention timeline

`app.pipeline.orchestrator.run_daily_inference` writes one
`intervention_log` row per day it produces a recommendation (existing
Phase 11 behavior, unmodified). Across the 30-day story the
recommendation engine's own primary target legitimately shifts: it
recommends `screen` (evening-screen reduction) from day 8 through
roughly day 18-19, then shifts to `meal` (earlier last meal) once the
real, unmodified contributor engine re-ranks meal timing above evening
screen (see the contributor-transition figure). This shift was not
engineered by this demo -- it is what the real recommendation engine
selected given the actual, improving behavior.

## 6. Compliance progression

Compliance is never hard-coded. For each day, once that day's own
`daily_observations` row exists (it always does here, since the whole
30-day schedule is seeded up front), `app.effectiveness.backfill.backfill_compliance`
is called -- the same function production code would call once a
day's behavior becomes available -- comparing the day's actual
behavior against the target the recommendation engine set. Compliance
degree genuinely varies day to day (observed range in the shipped run:
~0.32 to 1.0) as a direct function of how closely that day's authored
behavior happened to match the graduated target for that day, not a
fabricated ramp.

## 7. Expected vs. actual system behavior, and why the schedule was retuned

The first draft of this scenario used the brief's own illustrative
day-11..18 screen-cutoff numbers (12:15 AM -> 11:35 PM, a >2-hour
swing) and a first-guess DLMO seed. Running it end to end surfaced a
real, honest, but narratively undesirable emergent effect:

- `ideal_sleep_onset = fused_DLMO + phase_to_sleep_offset_hours` (2.0h,
  `app/alignment/config.py`) -- so phase alignment measures how close
  actual sleep onset is to *2 hours after* the estimated DLMO, not to
  the DLMO itself.
- The real state engine only ever moved the fused DLMO by roughly
  15-20 minutes total across the full 23-day change+response+stable
  window (it is bounded and slow-tracking by design -- see
  `docs/state_engine.md`'s continuity cap and adaptation rate).
- A >2-hour behavioral swing that fast overshoots what the
  participant's own (slowly-adapting) internal-clock estimate can
  track. Actual sleep onset raced ~2 hours earlier while
  `ideal_sleep_onset` barely moved, so the gap between them -- and
  therefore phase alignment, 60% of the total score -- **worsened**
  through most of the journey even though every individual behavioral
  component (screen, light, meals) genuinely improved.

Two retunings followed, **both driven by inspecting the actual
pipeline output, never by hard-coding a target score**:

1. The seeded `intrinsic_dlmo_time`/`adapted_dlmo_time`/`current_dlmo_time`
   (`app.scripts.seed_30day_demo`) were moved from an inconsistent
   first guess to values that make `ideal_sleep_onset` meaningfully
   earlier than the baseline's actual bedtime at day 1 (a real
   misalignment) and close to the improved bedtime by day 30 (a real,
   earned alignment gain).
2. The screen-cutoff swing (`SCREEN_END_ANCHORS` in the authoring
   script) was reduced from >2 hours to about 1 hour -- still a clear,
   visible improvement in every behavioral component, but within the
   range the real state engine can actually track inside a 30-day
   story.

A separate, unrelated fix: the original design put the demo's one
deliberate missing-data day on day 17. A single day's zeroed
window-completeness turned out to blank out `prediction_status` for
**six consecutive days** (a target day D's 6-day trailing window
includes day D-1..D-6, so a gap on day D affects predictions for days
D+1..D+6) -- which landed squarely on the required day-18 checkpoint.
The anomaly was moved to day 10 (whose impact window, days 11-16,
still avoids every required checkpoint) in an intermediate draft, then
dropped entirely in the shipped version to keep the primary story
clean, per the brief's own instruction not to overcomplicate the demo.

**No output was ever altered directly.** Every change described above
is a change to the *input* schedule or the *seed* biological state,
followed by a full pipeline rerun.

## 8. Actual system outputs (this release's shipped run)

See `release/demo_30day/demo_story.md` for the full checkpoint-by-checkpoint
report with real numbers, `release/demo_30day/daily_summary.csv` for
every day, and `release/demo_30day/figures/` for the 7 required
figures. Headline: mean alignment days 1-10 vs. days 25-30 improves
(see the story report for the exact numbers from the run that shipped
with this release -- intentionally not duplicated here to avoid two
sources of truth that could drift out of sync).

## 9. Why outputs are not hard-coded

`app.scripts.run_30day_demo` never writes to `circadian_labels`,
`alignment_results`, `contributor_results`, `recommendations`/
`intervention_log`, or `personal_effect_models` directly -- every
value in those tables comes from calling
`app.pipeline.orchestrator.run_daily_inference`,
`app.safety.engine.SafetyEngine.evaluate`,
`app.effectiveness.backfill.backfill_compliance`, and
`app.personalization.update.update_personalization_state`, the exact
same functions the real API uses. `tests/test_30day_demo.py` includes
an explicit test asserting the runner script's source contains none of
those tables' names anywhere near an `INSERT`/`session.add(...Result`
pattern for the intelligence tables (only for `Participant`/
`ParticipantProfile`/`DailyObservation`, the *inputs*).

## 10. Synthetic-data disclaimer

**This is a deterministic synthetic demonstration participant.**
Nothing about Arjun's story is a claim about any real person, and no
number in this scenario should be read as evidence of real-world
efficacy. Use "estimated biological clock", never "clinical DLMO"; use
"observed change", never "proven causal effect". See `README.md`
"Scientific boundary" and `docs/scientific_assumptions.md`.

## 11. How to reproduce

```bash
python -m app.scripts.seed_30day_demo --reset
python -m app.scripts.run_30day_demo
python -m app.scripts.validate_30day_demo
python -m app.scripts.generate_30day_demo_figures
```

Each step is idempotent-safe to rerun individually except the first
(`--reset` is required to reseed; omit it and the script refuses to
overwrite an existing database). The target database is always
`data/demo_30day_story.db` by default -- distinct from
`data/circadianiq.db` (the real dev DB) and `data/demo.db` (the
separate 4-scenario release demo) -- both `seed_30day_demo` and the
frozen-release scripts refuse to target each other's databases by
construction.

## 12. How to show the scenario in the frontend

No frontend code was changed. Point the API at the 30-day demo
database and load participant 9001 through the existing dashboard
route, exactly like any other participant:

```bash
# Windows PowerShell
$env:CIRCADIANIQ_DATABASE_URL="sqlite:///$PWD/data/demo_30day_story.db"
uvicorn app.api.main:app --reload
```

```bash
cd frontend && npm run dev
```

Then visit `http://127.0.0.1:5173/dashboard/9001`. The dashboard reads
the same `/api/v1/participants/9001/status` (and history/contributors/
recommendation/interventions) endpoints as every other participant --
no special "demo mode" exists anywhere in the API or UI code.
