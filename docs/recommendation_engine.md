# CircadianIQ Recommendation Engine (Phase 10)

## 1. Purpose

Converts Phase 9's ranked contributors into **1 primary intervention +
up to 2 supporting nudges** -- never three equal-priority
recommendations. A deterministic, database-driven selection system:
no LLM, no free-form text generation, no hidden randomness. It picks
*which* behavioral action to suggest and *how large a step* to ask
for; it does not measure whether an intervention actually worked
(a later effectiveness phase), does not personalize beyond the
interface stubs described in section 12, and does not run any safety
check (Phase 14).

## 2. Deterministic architecture

```
TOP CONTRIBUTORS (Phase 9) + MISALIGNMENT SEVERITY (Phase 8's score)
+ INTERVENTION CATALOGUE (database) + EXPECTED IMPACT + FEASIBILITY
+ GRADUATED TARGET + PERSONALIZATION PHASE
    -> 1 PRIMARY INTERVENTION + 2 SUPPORTING NUDGES
```

Entry point: `app.recommendations.engine.select_recommendations(inputs, config)`.
Given the same `RecommendationInputs`, it always returns the same
`RecommendationResult` (verified by
`test_select_recommendations_is_deterministic`).

## 3. Candidate intervention catalogue

The catalogue is **only** the `recommendations` table
(`app.database.models.Recommendation`), seeded by
`app.database.seed._REFERENCE_RECOMMENDATIONS` -- this phase never
hard-codes a second Python catalogue. Six interventions are seeded:
morning light, evening screen reduction, consistent sleep schedule
(social jetlag), earlier last meal, exercise timing, and late-caffeine
reduction.

Each row's `extra_metadata` JSON column carries the structured fields
the engine needs (`app.recommendations.catalogue.CandidateIntervention`):
`contributor_signals`, `value_kind`, `direction`, `template`,
`desired_value_assumption` (+ `desired_value_relative_to`),
`max_shift_per_recommendation`, `min_target_value`/`max_target_value`,
`baseline_feasibility`, `severity_applicability`, and
`is_literature_verified`.

**Disclosure**: every numeric value in the seeded catalogue --
`literature_expected_improvement_minutes` included -- is a **project
design placeholder** for demonstrating the engine end-to-end, not a
verified literature citation. Each row's `source` field says so
explicitly. `REDUCE_LATE_CAFFEINE` deliberately has an empty
`contributor_signals` list: caffeine timing is not one of Phase 9's
five ranked signals, so it stays in the catalogue for completeness but
is only ever chosen via the no-signal-match fallback (section 10).

## 4. Severity model

Bands are computed from Phase 8's `final_score` -- a **project design
choice**, not a clinical cutoff (`app.recommendations.severity`):

| Band | Alignment score |
|------|------------------|
| `good` | >= 80 |
| `mild` | 60 <= score < 80 |
| `moderate` | 40 <= score < 60 |
| `severe` | < 40 |

## 5. Impact/feasibility weighting

Severity decides how strongly the engine trades off expected impact
against feasibility (`app.recommendations.config.RecommendationConfig`):

| Severity | impact_weight | feasibility_weight |
|----------|---------------|----------------------|
| `severe` | 0.55 | 0.45 |
| `moderate` | 0.45 | 0.55 |
| `mild` | 0.35 | 0.65 |
| `good` | 0.20 | 0.80 (maintenance-only bias) |

## 6. Contributor relevance

An intervention's `contributor_signals` are matched against the
participant's **top-3, significant** Phase 9 contributors
(`app.recommendations.relevance`). Relevance is keyed by the matched
contributor's rank (`relevance_by_rank = (1.0, 0.6, 0.3)`); a signal
matched only among the imputed-data candidates is scaled down
(`imputed_data_relevance_multiplier`, default 0.6) rather than
excluded outright, and one matched from a wholly `"unavailable"`
contributor scores 0. An intervention addressing more than one
significant contributor gets a small consolidation bonus
(`multi_signal_relevance_bonus = 0.15`) rather than being penalized --
preferred over recommending two near-duplicate actions. A candidate
below `min_relevance_threshold` (0.25) is dropped from consideration
unless *no* candidate clears the threshold at all, in which case the
engine falls back to the best-scoring candidate overall (see section
10's "no available intervention" case).

## 7. The candidate-scoring equation

```
candidate_score =
    contributor_relevance
    * (impact_weight * normalized_expected_impact + feasibility_weight * normalized_feasibility)
    + personalization_score_adjustment
    + continuation_bonus
```

`normalized_expected_impact` is max-scaled to `[0, 1]` across the
candidate set being compared (`app.recommendations.scoring.normalize_max_scale`
-- the same transparent max-scaling pattern Phase 9 uses for effect
normalization). `normalized_feasibility` is already defined on `[0, 1]`
by construction (section 9), so it is used directly.

## 8. Graduated target logic (locked rule)

**Never ask for the theoretically ideal value immediately.** Target
roughly halfway between the current behavior and the desired value
(`graduated_target_fraction = 0.50`,
`app.recommendations.targets.compute_graduated_target`):

```
target = current + fraction * (desired - current)              (linear, e.g. light duration)
target = add_hours(current, fraction * circular_diff_hours(desired, current))   (clock-time, e.g. screen cutoff)
```

Clock-time-valued behaviors use the existing circular-time utilities
(`app.synthetic.time_utils.circular_diff_hours` / `add_hours`), so a
gap crossing midnight is interpreted as the short way around, never a
naive 20+ hour linear difference.

### Worked midnight example

Current screen cutoff: 01:30 (`1.5`). Desired: 22:30 (`22.5`).
`circular_diff_hours(22.5, 1.5) = -3.0` -- the shortest path from 01:30
to 22:30 is *backward* 3 hours, not forward 21. At `fraction = 0.5`:
`shift = -1.5h`, `target = add_hours(1.5, -1.5) = 0.0` = **00:00**.
Recommendation: *"Try stopping screens by 12:00 AM."* -- never
"Stop screens by 10:30 PM." (Verified exactly by
`test_midnight_example_matches_worked_example_in_docs`.)

### Target bounds and direction

- `max_shift_per_recommendation` (catalogue-declared, minutes/hours
  depending on `value_kind`) clips how large a single graduated
  shift can be, regardless of how big the theoretical gap is.
- `min_target_value` / `max_target_value` additionally clip the final
  target for non-circular (duration) behaviors.
- If a catalogue entry declares no bounds, `default_max_shift_minutes`
  (a conservative, explicitly-labeled project default -- not a safety
  limit) applies.
- Each intervention declares a `direction` (`earlier`/`later`/
  `increase`/`decrease`). If the participant's current behavior is
  already past the desired direction (e.g. screen cutoff already
  earlier than the target), the gap is clamped to zero --
  **never recommend moving backwards** to "catch up" to a stale
  target.

## 9. Feasibility

`app.recommendations.feasibility.compute_feasibility` combines:
the catalogue's `baseline_feasibility`, a pull toward/away from that
baseline from recent compliance history (`compliance_feasibility_weight`),
a penalty proportional to how much of the intervention's own shift
bound the graduated target actually uses
(`target_difficulty_feasibility_weight`), and a flat penalty
(`recent_failure_feasibility_penalty`) if the same intervention was
recently logged non-compliant. A transparent heuristic, not fit to
data -- superseded by a later effectiveness/personalization phase.

## 10. Primary vs. supporting selection

1. Filter candidates: active, severity-applicable, not a duplicate
   `intervention_id`.
2. Evaluate every remaining candidate (relevance, current value,
   graduated target, feasibility, expected improvement).
3. Restrict to candidates at/above `min_relevance_threshold`; if
   **none** clear it (the participant's top contributor has no
   catalogue match at all), fall back to the full evaluated set so a
   recommendation is still produced rather than nothing.
4. Sort by `candidate_score` descending; the top entry is primary,
   subject to the cooldown override (section 11).
5. Remove candidates that conflict with the chosen primary (same
   `intervention_id`, or a fully-redundant match to the exact same
   contributor signal(s) the primary already covers).
6. Take up to `max_supporting_recommendations` (2) of what remains,
   assigned priorities 2 and 3.

Never three priority-1 recommendations; `supporting` may be shorter
than 2 if fewer valid candidates remain.

## 11. Intervention history & cooldown

Not a medical treatment schedule -- a simple adherence heuristic
(`app.recommendations.cooldown`). If the same intervention was primary
within `primary_cooldown_days` (5), it receives a `continuation_bonus`
(0.08) so a marginally higher-scoring alternative doesn't needlessly
displace it. It is still replaced outright if its own score (bonus
included) falls below `continuation_minimum_relative_score` (70%) of
the best alternative's score -- cooldown favors stability, not
stubbornness. Recent compliance history (section 9) separately feeds
feasibility; a recently-failed intervention is not automatically
banned, just scored lower.

## 12. Personalization compatibility

Four personalization-phase values are accepted
(`app.recommendations.personalization`), with this phase implementing
only the interface, not the learning:

- **`literature`** (default): the catalogue's own expected-improvement
  value is used as-is.
- **`personal_ranking`**: an externally computed per-intervention
  ranking score is blended additively into `candidate_score`; the
  *stated* expected improvement stays literature-sourced.
- **`personal_effect`**: an externally computed per-intervention
  expected improvement replaces (or, if configured, averages with)
  the literature value, and `expected_improvement_source` becomes
  `"personal"` (or `"blended"`).
- **`adaptive_policy`**: accepted for forward interface compatibility
  with a future contextual-bandit phase only; behaves identically to
  `literature` today.

No contextual bandit, no personal-effect model fitting, is implemented
in this phase.

## 13. Template system

Templates live in the catalogue (`extra_metadata["template"]"`);
`app.recommendations.templates.render_template` only fills in
`{target_time}` / `{target_value}` / `{current_value}` /
`{expected_improvement}` placeholders with already-formatted strings
(clock times as `"10:00 PM"`, never a raw float hour). An unrecognized
placeholder is left visibly untouched rather than raising. No LLM is
ever invoked to write recommendation text.

## 14. Missing-data behavior

If a candidate's mapped behavior has no resolvable current value in
the six-day window (`app.recommendations.behavior.resolve_current_value`
returns `None`), the candidate is **excluded outright** --
never a fabricated value. If the matched contributor's Phase 9
`data_quality` is `"imputed"`, relevance is reduced
(`imputed_data_relevance_multiplier`) rather than the candidate being
silently treated as fully reliable; `"unavailable"` zeroes relevance
for that match entirely. This reuses Phase 9's existing data-quality
accounting rather than inventing a second, incompatible confidence
system.

## 15. Safety boundaries

Recommendations stay strictly behavioral: screen timing, natural light
exposure timing, meal timing, exercise timing, caffeine timing. Never
medication, melatonin dosing, or any diagnosis-based treatment --
verified by `test_no_medical_or_medication_language_in_seeded_catalogue`
scanning the catalogue for banned terms. A further safety gate is
Phase 14's responsibility, not this phase's.

## 16. Limitations

- All severity thresholds, weights, relevance/feasibility parameters,
  and the graduated-target fraction are locked **project design
  choices**, not independently validated.
- Every catalogue numeric assumption (desired targets, expected
  improvement, feasibility baselines) is an explicitly-labeled
  placeholder, not a cited literature value.
- Exercise-timing direction is fixed as "earlier" (move away from
  bedtime); the engine does not detect whether a participant's
  exercise timing problem is actually "too early" instead -- a
  documented scope limitation.
- Feasibility is a simple heuristic, not fit to any real compliance
  data.

## 17. Synthetic-data interpretation warning

`python -m app.scripts.run_recommendation_diagnostics` distributions
(primary-intervention frequency, severity distribution, personality
breakdown) are properties of the Phase 3 synthetic generator's
construction and this phase's own placeholder catalogue values -- not
evidence about real human intervention effectiveness or prevalence.

## Worked example

A participant is `moderate` severity (alignment score 55), with
Phase 9's top contributor `evening_screen` (significant, rank 1) and
second `social_jetlag` (significant, rank 2). Current screen cutoff
(derived from sleep onset minus mean screen duration): 01:24. Ideal
sleep onset: 21:45. Desired cutoff: 21:15 (`ideal - 0.5h`). Graduated
target (halfway): approximately 23:20.

- **Primary**: `EVENING_SCREEN_REDUCTION` -- *"Try stopping screens by
  11:20 PM."* Expected improvement: ~15 min (literature-sourced
  placeholder). Contributor signal: `evening_screen`.
- **Supporting #1**: `CONSISTENT_SLEEP_SCHEDULE` -- addresses the
  second significant contributor (`social_jetlag`).
- **Supporting #2**: `MORNING_LIGHT_EXPOSURE` -- a lower-burden nudge
  that does not conflict with the primary's contributor signal.

`REDUCE_LATE_CAFFEINE` and `AFTERNOON_EXERCISE_TIMING` are evaluated
but excluded from the top 3 in this example: caffeine has no matching
Phase 9 contributor signal (near-zero relevance), and exercise's own
Phase 9 contribution was not among this participant's significant
top-3 contributors this window.
