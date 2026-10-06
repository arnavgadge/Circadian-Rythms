# CircadianIQ Synthetic Data Generation (Phase 3)

## 1. Purpose

This phase generates a synthetic but biologically motivated 30-day
longitudinal dataset -- 1,000 participants x 30 days = 30,000
participant-day records, and 24 six-day-window-to-next-day-target
records per participant (24,000 total) -- for later phases to train
and validate a DLMO-estimation model against.

It produces exactly three things, and nothing more:

1. **Raw synthetic longitudinal data** (daily behavioral/environmental
   observations, written to `daily_observations` and, separately,
   `physiology_logs`).
2. **Daily stateful DLMO labels** (the synthetic ground-truth circadian
   phase trajectory, written to `circadian_labels` with
   `prediction_status="synthetic_ground_truth"`).
3. **Sliding-window metadata** (which 6 days of behavior map to which
   next-day target, exported as a derived Parquet artifact -- see
   section 9).

It does **not** compute ML features, train anything, run alignment or
contributor logic, or select recommendations. Those are later phases.

## 2. Participant generation

`app.synthetic.population.generate_participants` runs once per
participant, before any of the 30 days are simulated, and assigns:
`participant_code`, `chronotype`, `personality_key`, `meq_score` (+
category), intrinsic/initial-adapted/initial-current DLMO, a stable
`baseline_sleep_onset_hour` trait, and the three sensitivity
multipliers. Nothing here changes once the 30-day simulation starts.

Chronotype and personality are assigned via **exact stratified
sampling** (`_stratified_assignment`): rather than drawing each
participant's category independently (which would only
*approximately* match the configured proportions), the exact integer
counts implied by the proportions are computed once (with
largest-remainder rounding), assembled into a label list, and shuffled
with a reproducible RNG. At the default N=1,000, both the chronotype
split (27/59/14%) and the personality split (8/10/25/12/15/18/12%) are
exact integers, so the realized population matches the configuration
exactly, not just approximately.

## 3. Chronotype generation

Three user-facing categories: **Early**, **Intermediate**, **Late**.
Population proportions (27% / 59% / 14%) and the DLMO mean/SD per
chronotype are **source-backed** (see section 11). Chronotype is a
fixed trait -- it never changes across the 30 days. Intrinsic DLMO is
drawn once from `Normal(mean_by_chronotype, sd_by_chronotype)`; initial
`adapted`/`current` DLMO start within a small random nudge
(`Normal(0, 0.10h)`) of intrinsic, per the "close to intrinsic at
onboarding, plus small participant-specific variation" requirement.

## 4. MEQ generation

MEQ is drawn once per participant from a chronotype-conditioned normal
distribution (early -> higher mean, late -> lower mean; see
`population._MEQ_MEAN_BY_CHRONOTYPE`), clipped to the real MEQ
instrument's [16, 86] range, and held fixed for the whole 30-day
period (it is a stable subjective trait, not a daily-varying signal).
The chronotype-specific target means/SDs used to draw it are a
**synthetic** mapping -- the project's sources give the instrument's
range, not per-chronotype means. `MEQ_normalized` and
`MEQ_MSFsc_divergence` are explicitly **not** computed here; they are
Phase 4 feature-engineering outputs. The standard Horne & Ostberg
(1976) category bands (definite/moderate evening, intermediate,
moderate/definite morning) are stored as `meq_category`.

## 5. MSFsc generation

MSFsc is corrected mid-sleep on **free days** -- not sleep onset, and
not conflated with it anywhere in this codebase. Each day's raw sleep
onset/offset/midpoint is stored in `daily_observations`; on days that
are free days, the same values are *also* stored in the dedicated
`free_day_sleep_onset_time`/`free_day_sleep_offset_time`/
`free_day_sleep_midpoint_time` columns, so a later phase can select
free-day midpoints directly without re-deriving "was this a free day"
logic. `participant_profiles.msfsc_time` stores a participant-level
baseline: the **circular mean** of that participant's free-day sleep
midpoints across all 30 days.

This is a deliberate simplification: the officially defined MCTQ MSFsc
correction (which adjusts for oversleep on free days relative to sleep
debt accumulated on workdays) is **not** implemented, because no
project source specifies its exact formula and inventing one would
violate the no-fabricated-coefficients rule. What is stored is the
uncorrected free-day sleep-midpoint average, clearly named
`msfsc_baseline_hour` internally / `msfsc_time` in the database --
close to, but not identical to, a textbook MSFsc. A later phase can
apply the correction if/when a source for it is found, using the raw
per-day free-day fields already stored.

## 6. Behavioral personalities

Seven personalities, assigned independently of chronotype (see section
2), with **synthetic** population proportions:

| Personality | Proportion | Defining traits |
|---|---|---|
| Consistent early bird | 8% | Earlier sleep/light/meals, low social jetlag, low evening screen |
| Consistent night owl | 10% | Later sleep/wake/light/screen-cutoff/meals |
| Social jetlag student | 25% | Near-normal weekdays, large weekend sleep shift, high social jetlag |
| Chaotic sleeper | 12% | High day-to-day timing variance, frequent large disruptions |
| Healthy stable routine | 15% | Consistent sleep, strong morning light, low evening screen |
| Screen-heavy user | 18% | Long evening screen duration, late cutoff, otherwise ordinary |
| Late eater | 12% | Disproportionately late last meal, otherwise ordinary |

Every numeric parameter for each personality (`app.synthetic.
personalities.PERSONALITY_PROFILES`) is a synthetic design choice
calibrated only to produce the qualitative shape described above and
in the project brief -- none of it is survey- or literature-derived.
All timing fields are expressed as **offsets from the participant's
own stable baseline sleep-onset trait** (itself anchored once to
intrinsic DLMO -- see section 8), so a personality shapes behavior
relative to that participant's own biology rather than to an absolute
clock time shared by everyone.

## 7. Daily behavior generation

`app.synthetic.behavior.generate_daily_behavior` computes one day as:
**personality baseline + weekday/weekend effect + day-level stochastic
noise + occasional disruption event** -- and nothing else. It never
reads `current_DLMO`. This is the single most important design
decision in this phase: behavior is the causal *input* to the
biological state model (section 8), so if behavior were generated from
the evolving state, the dataset would encode a circular
`DLMO -> behavior -> DLMO` loop that would make later supervised
learning trivially "solve" a problem the generator itself had already
solved, invalidating the whole exercise.

Weekday/weekend is determined from the calendar date
(`date.weekday()`); Saturday/Sunday are treated as free days, a
scheduling simplification, not a claim about any real participant's
actual week. Windowed/aggregate quantities that a *single* day cannot
determine on its own -- `free_day_ratio`, MSFsc itself -- are left
`NULL` in `daily_observations`; `sleep_midpoint_variability_minutes`
is the one exception, computed as the single-step (yesterday-to-today)
absolute circular change, since that only needs the immediately
preceding day, not a full window. Physiology (`resting_hr_bpm`,
`hrv_ms`, `wrist_temp_c`) is generated as independent, non-causal
noise -- it never feeds into the DLMO state model, and later phases
must not silently treat it as a Version-1 behavioral input either.

## 8. The DLMO state model

`app.synthetic.dlmo_state` owns the three-layer state:
`intrinsic -> adapted -> current`. `intrinsic_DLMO` never changes.
Each day, in date order, `step()`:

1. Computes that day's total behavioral effect (minutes; positive =
   delay, negative = advance) from morning light, evening screen, last
   meal, exercise, and caffeine (section 9), scaled by the
   participant's stable sensitivity multipliers, then clips the total
   to **[-90, +60] minutes** -- a synthetic simulation-stability bound,
   not a physiological ceiling.
2. Updates `current_DLMO`: previous `current` + the day's clipped
   effect + a pull toward `adapted_DLMO`
   (`current_daily_pull_to_adapted_fraction`) + small state noise,
   clipped to stay within **+/-3 hours** of intrinsic.
3. Updates `adapted_DLMO` (slower): a small pull toward the day's
   behavioral direction (~1%/day,
   `adapted_daily_pull_to_behavior_fraction`) plus a small pull back
   toward intrinsic (~0.5%/day,
   `adapted_daily_pull_to_intrinsic_fraction`), clipped to **+/-2
   hours** of intrinsic.

Critically, day N's state is computed **from day N-1's state**, never
recomputed from a fresh window of days -- see `app.synthetic.
simulator.generate_synthetic_dataset`'s single sequential loop per
participant, and `tests/test_synthetic_dlmo_state.py::
test_state_update_depends_on_previous_state_not_just_behavior`, which
proves the same day's behavior produces different results depending on
where the state started. All three numeric rates/bounds above, and the
daily clip, are **synthetic** (see section 11) -- kept in one place
(`SyntheticAssumptions`) rather than scattered through the code.

The connection between `baseline_sleep_onset_hour` (used by every
personality as its timing anchor -- section 6) and intrinsic DLMO is
the one place a source-backed relationship is used at the *trait*
level: `sleep_onset = DLMO + 2h (+/- 1h noise)` (project document
section 5.2), applied **once**, at onboarding, against the fixed
intrinsic DLMO -- never against the evolving current state, which
would reintroduce the forbidden feedback loop.

## 9. Interaction effects

Three interactions, exactly as specified in the project brief, all
synthetic multipliers with no literature source:

1. **No morning light amplifies the evening-screen delay** (x1.25).
2. **High morning light reduces the evening-screen effect** (x0.5;
   moderate light reduces it x0.75).
3. **A "late habitual sleeper" with a very late last meal (after
   23:00) has the meal delay amplified** (x1.3). "Late habitual
   sleeper" is defined from the participant's *stable baseline* sleep
   onset trait (more than 1.5h past a 22:00 reference, in the forward/
   later circular direction) -- a per-participant trait check, not a
   per-day one.

Each of the five signal effect functions
(`app.synthetic.dlmo_state._morning_light_effect_minutes`,
`_evening_screen_effect_minutes`, `_last_meal_effect_minutes`,
`_exercise_effect_minutes`, `_caffeine_effect_minutes`) is a smooth,
saturating (exponential) function of dose/timing rather than a
discrete lookup table, calibrated so its low/high asymptotes match the
source-backed anchor ranges where one exists (light, screen, meal);
the curve *shape* and time constants are synthetic interpolation. The
four-tier (light) and five-tier (screen) and five-tier (meal)
"signal tiers" from the project brief are implemented as a single
reusable `classify_tier()` helper plus the interaction rules above,
not scattered conditionals -- and are used for classification/
diagnostics, while the DLMO *effect* itself always comes from the
continuous curve, so tiering and effect computation cannot drift out
of sync.

## 10. Stochasticity

`app.synthetic.rng.RandomStreams` splits one master seed into seven
independent named streams (`population`, `personality`, `sensitivity`,
`behavior`, `disruption`, `state`, `physiology`) via NumPy
`SeedSequence.spawn`, and further splits each into one
deterministic sub-stream per participant
(`RandomStreams.participant_stream`) using only integers (the stream's
fixed index and the participant's index) -- **never** Python's
randomized `hash()`, which would silently break cross-process
reproducibility. Changing, say, the physiology noise model cannot
perturb sleep-timing draws, because they come from different streams;
regenerating with the same seed reproduces the exact same dataset (see
section 14).

Included noise sources: participant-level (chronotype/MEQ/sensitivity
draws), day-level (`day_level_noise_sd_minutes` in the DLMO effect;
`timing_noise_sd_hours` per personality in behavior), and occasional
disruption events (`disruption_probability x
disruption_probability_multiplier` per personality, applying a
uniform-magnitude random-sign shift to that day's sleep onset).

## 11. Assumptions vs. literature

Every number in `app.synthetic.config` is labeled one of two ways.

**Source-backed** (`SourceBackedAssumptions`) -- taken from
`CircadianIQ_Project_Document.docx` section 5, which cites:

- Chronotype population split (27/59/14%) and social jetlag
  distribution (mean 1.0h, SD 0.75h, 70% >=1h, ~50% >=2h): PMC6595939;
  Wittmann et al., *Chronobiology International* 2006.
- DLMO-by-chronotype means/SDs: Hunger et al. (PMC10743549).
- Sleep-onset/DLMO relationship (`DLMO ~ sleep_onset - 2h`, +/-1h
  noise, r=0.89): Frontiers in Neurology (2010); Oxford *Sleep*
  (zsab126).
- Morning light -> phase advance ranges: PMC10594521; PubMed 25620199.
- Evening screen -> phase delay ranges: PMC12668929; PMC10594521.
- Late meal (after 9pm) -> phase delay range: PMC6471585.
- MEQ instrument range [16, 86]: Horne & Ostberg (1976), the standard
  published MEQ scale -- an instrument property, not a project finding.

This code has not independently re-verified those cited papers; it
treats the project's own document as the source of record, per the
instruction to reference existing project documentation accurately
rather than re-deriving or inventing citations. If any of those
citations turns out to be wrong, section 5 of
`CircadianIQ_Project_Document.docx` is the place to correct it, and
`SourceBackedAssumptions` should be updated to match.

**Synthetic** (`SyntheticAssumptions`) -- everything else: personality
proportions and every personality parameter, sensitivity distributions
and their clip range, the three-layer state update's rates and bounds,
the daily shift clip, the interaction multipliers, the response
curves' shapes/time-constants, the exercise/caffeine effect model in
full (no project source covers either signal at all), the
weekday/weekend calendar convention, and the physiology noise model.
None of these are presented as literature-derived, anywhere in the
code or in this document.

**Random variability** is never a fixed number -- it always appears in
the code as an explicit draw from a named distribution
(`rng.normal(...)`, `rng.uniform(...)`), never as a silent fudge added
to a formula.

An unresolved scientific choice worth flagging: personality and
chronotype are generated independently, so combinations like an
"Early" chronotype paired with a "consistent night owl" personality
are possible (and were observed in testing -- see the deliverable
report). This is intentional (it represents behaviorally-driven
misalignment against one's own biological tendency, which is
realistic), but it was not a coefficient anyone published; it is a
structural modeling choice.

## 12. Temporal ordering and leakage

For a window ending on day N-1 with target day N:

- The window's **features** may only use days N-6 .. N-1 (six days).
- The **target** is `current_DLMO` *as of* day N -- i.e. the state
  produced by applying day N's own state transition. Day N's *behavior*
  is real and stored, but it belongs to day N, not to the N-6..N-1
  feature window.
- `_build_windows()` enforces `feature_end_date < target_date` with a
  fixed one-day gap and a fixed five-day span
  (`tests/test_synthetic_dataset.py::
  test_window_dates_never_include_the_target_date_in_the_feature_span`
  checks this directly) -- day N's behavior is never a feature for
  predicting day N's target, and no day used as a feature ever
  postdates the target.

This is the only ordering guarantee Phase 3 makes. Turning the 6-day
feature window into the actual 68-feature ML representation (encoding,
aggregation, imputation) is entirely Phase 4's responsibility.

## 13. Reproducibility

The exact same `SimulationRunConfig` (seed, participant count, day
count, window size, start date) reproduces the exact same dataset --
verified by `tests/test_synthetic_dataset.py::
test_same_seed_is_fully_reproducible` (in-memory) and `tests/
test_synthetic_db_writer.py::
test_regenerated_data_with_same_seed_writes_equivalent_rows` (through
a full database round-trip). Reproducibility depends on: (a) the
`RandomStreams` design (integer-only stream derivation -- section 10),
and (b) exact stratified assignment being order-stable given a fixed
permutation seed.

Each generation run's metadata -- seed, participant count, day count,
`generator_version`, `config_version`, and a UTC timestamp -- is
recorded in two places: `data/synthetic/generation_manifest.json`
(the authoritative record for the *run*, written by
`app.synthetic.export.build_manifest`) and, redundantly, inside each
participant's `participant_profiles.synthetic_personality_profile`
JSON blob under a `"generation"` key (a convenience copy, since that
field already exists in the Phase 2 schema for exactly this kind of
variable synthetic-data metadata).

## 14. Validation checks

`app.synthetic.validation.run_quality_checks` runs 16 automated checks
against a generated dataset: exact participant/day/row/window counts,
no duplicate (participant, date) pairs, no missing required fields, all
DLMO values within a valid circular range, plausible sleep/screen/meal/
physiological values, chronotype and personality distributions
recorded, social jetlag differing meaningfully across personalities,
and DLMO state continuity plus the adapted/current bound constraints
holding across the whole dataset. The CLI (`python -m app.scripts.
generate_synthetic_data`) runs these automatically and refuses to write
to the database if any check fails.

## 15. Where things live (module map)

```
app/synthetic/
    config.py          SourceBackedAssumptions / SyntheticAssumptions / SimulationRunConfig
    time_utils.py       circular time utilities (diff, mean, std, hour<->time conversion)
    rng.py              reproducible, subsystem-separated random streams
    population.py       chronotype / MEQ / sensitivities / stable traits
    personalities.py    the seven PersonalityProfile definitions
    behavior.py         independent daily behavior generation
    dlmo_state.py       the three-layer state model + effect/interaction functions
    simulator.py        orchestration: participants -> days -> state -> DataFrames
    validation.py       the 16 automated quality checks
    diagnostics.py      distribution report + 6 diagnostic plots
    export.py           Parquet/JSON derived-artifact export + manifest
    db_writer.py         writes the dataset into the Phase 2 schema

app/scripts/generate_synthetic_data.py   CLI entry point
```
