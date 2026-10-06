# CircadianIQ Long-Term Personalization Engine (Phase 13)

## 1. Personalization objective

Progressively learn which interventions work best for an individual,
**based on historical evidence only** -- never because an intervention
was merely recommended, liked, or looks important to a model. Evidence
comes from intervention exposure + compliance + observed outcomes,
consumed from Phase 12's effectiveness analysis. This phase produces
*evidence and adjustments*; Phase 10 still owns primary/supporting
selection.

## 2. Cold start

A brand-new participant/intervention-type pair has zero
`intervention_log` history -> `get_personalization_phase` returns
`literature` immediately (`app.personalization.phases.phase_from_evidence`).
No special-casing is needed: the same evidence-count/weeks-active gate
that governs every later transition naturally returns `literature`
when both are zero.

## 3. Phase 1: personal ranking

Activates once **both** gates clear (defaults: `ranking_min_observations=3`,
`ranking_min_weeks_active=3`):

```
personal_score = |personal_effect_estimate| x compliance_probability
```

`personal_effect_estimate` is **consumed** from Phase 12's most
recently persisted `intervention_effect_estimates` row for that
intervention type (preferring Phase 3 > Phase 2 > Phase 1, whichever
Phase 12 actually reached) -- never recalculated here.
`compliance_probability` (`app.personalization.compliance_probability`)
is the mean of historical `compliance_degree` values, a dimension kept
explicitly separate from effect magnitude: a high-effect/low-compliance
intervention and a low-effect/high-compliance one can both plausibly
rank first, entirely depending on the product.

Each candidate also carries an **evidence-strength** label
(`app.personalization.phases.classify_evidence_strength`) -- `insufficient`
(<3) / `weak` (3-6) / `emerging` (7-13) / `moderate` (14-20) /
`stronger` (21+). These are engineering metadata for transparency, not
statistical-significance categories.

## 4. Phase 2: personal effect model

Activates at `effect_model_min_observations=14` and
`effect_model_min_weeks_active=6`. The line

```
effect = slope x compliance + intercept
```

reuses **exactly** Phase 12's Phase 3 regression output: `slope` =
`effect_mins_per_compliance_unit`, `intercept` = that same regression's
own fitted intercept coefficient (`diagnostics["coefficients"]["intercept"]`).
No second regression is fit (`app.personalization.effect_model` only
extracts and validates, never refits) -- Phase 12's regression already
includes compliance as a covariate, so re-deriving the line here would
be a duplicated, and possibly inconsistent, calculation.

## 5. Phase 3: contextual adaptive policy

Activates at `adaptive_min_observations=42` and
`adaptive_min_weeks_active=12` (~3-4 months). A lightweight **contextual
bandit with Thompson sampling** (`app.personalization.bandit`) --
explicitly not generic reinforcement learning. Per-participant/
intervention-type posterior state (`posterior_mean`, `posterior_variance`,
`total_pulls`, `total_reward`) lives in the existing `bandit_state`
table, updated via a standard **Normal-Normal conjugate Bayesian
update** (a textbook formula, not a custom heuristic):

```
posterior_variance' = 1 / (1/posterior_variance + 1/obs_variance)
posterior_mean'     = posterior_variance' * (posterior_mean/posterior_variance + reward/obs_variance)
```

Action selection samples each arm's posterior
(`app.personalization.bandit.thompson_sample`) and picks the
highest-sampled arm, **except** an exploration safeguard: an arm whose
posterior mean dominates every other arm's by more than
`exploration_dominance_margin` is never displaced by a single lucky
sample from a long-shot arm (`select_action`). Candidate actions are
always restricted to the approved behavioral catalogue -- the bandit
never invents an action outside it.

## 6. Evidence thresholds

All numeric thresholds below are **project engineering graduation
rules**, not statistical or clinical requirements
(`app.personalization.config.PersonalizationConfig`):

| Phase | Min. observations | Min. weeks active |
|---|---|---|
| `personal_ranking` | 3 | 3 |
| `personal_effect` | 14 | 6 |
| `adaptive_policy` | 42 | 12 |

## 7. Literature blending

`app.personalization.blending.blend_effect`:

- No personal effect, or the personal model fails validity ->
  100% literature.
- Personal effect valid but `< full_personal_min_observations` (21) ->
  `0.40 * personal + 0.60 * literature` (the locked blend).
- Personal effect valid and `>= 21` observations -> 100% personal.

## 8. Compliance interaction

Compliance probability and biological effect are **always** two
separate numbers multiplied together, never conflated -- see section 3.
A participant who reliably follows a weak-effect intervention and one
who rarely follows a strong-effect intervention can score similarly;
the ranking score reflects the realistic expected outcome (what
actually tends to happen), not the theoretical best case.

## 9. Effect estimation source

Preference order, entirely determined by what Phase 12 actually
computed for this intervention type (never chosen by Phase 13):
Phase 3 regression > Phase 2 matched-period > Phase 1 observational >
literature. `PersonalRankingEntry.evidence_source` records which one
was used.

## 10. Intervention-specific graduation

Every function in this phase takes an explicit `intervention_type`
argument and reads/writes state keyed by
`(participant_id, intervention_type)` -- there is no global
per-participant phase. `personalize_recommendations` returns
`phase_by_intervention_type: dict`, so "Arnav + morning light:
PERSONAL_EFFECT, Arnav + screen: PERSONAL_RANKING, Arnav + meal:
LITERATURE" is representable and expected, not an edge case.

## 11. Temporal leakage prevention

Every read in `app.personalization.db_adapter` takes an explicit
`as_of_date` and filters strictly (`log_date < as_of_date`,
`period_end < as_of_date` or `NULL`) -- a recommendation being
personalized for day 31 can only ever see evidence from days before
day 31, never day 31 itself or later. This is verified directly:
`count_compliance_observations(..., as_of_date=day_31)` on a 40-day
injected history returns exactly 30 (days 0-29), and the same query at
an earlier cutoff returns a strictly smaller count than at a later one
over the same underlying data.

## 12. Bandit reward

Uses the **same signed-DLMO convention** already established in
Phases 6-9 (positive minutes = delay, negative = advance; a positive
Phase 8 `phase_deviation_minutes` means the participant needs an
advance). "Improvement" is relative to what *this specific participant*
currently needs, not a blind sign rule:

```
corrective_sign = -1 if phase_deviation_minutes > 0 else +1
reward = (signed_effect_minutes * corrective_sign) * compliance
```

An intervention that advances someone who is already too advanced
produces a *negative* reward, exactly mirroring Phase 9's
aggravating-vs-corrective direction logic, expressed here as a
continuous magnitude rather than a category label.

## 13. Exploration safeguards

See section 5 -- `exploration_dominance_margin` prevents the bandit
from ever sacrificing a clearly superior, well-evidenced intervention
for an uncertain long-shot. Verified by
`test_exploration_never_overrides_a_dominant_arm` (50 repeated trials,
the dominant arm always wins despite the long-shot's huge variance).

## 14. Database state

- `personal_effect_models` (Phase 2 table, four columns added by
  migration `bd2e1f4a9c31`: `confidence_interval_lower/upper`,
  `model_version`, `evidence_source`) -- **current-state**, upserted in
  place per `(participant_id, intervention_type)`, mirroring
  `participant_profiles`. The auditable history of *how* an estimate
  was derived lives in Phase 12's immutable `intervention_effect_estimates`
  log, not a second versioned copy here.
- `bandit_state` (unchanged) -- current posterior per
  `(participant_id, intervention_type)`.

## 15. Recommendation-engine integration

`app.personalization.dispatcher.personalize_recommendations` returns
`personalized_ranking` / `personal_expected_improvement` dicts keyed
exactly by `intervention_id`, matching
`app.recommendations.inputs.RecommendationInputs`'s existing fields
(built for exactly this purpose in Phase 10). Because Phase 10 resolves
expected improvement under a single `personalization_phase` value per
call, Phase 13 picks one **effective** phase for the call (the most
advanced one with any populated adjustment) rather than mixing modes
per candidate; `ADAPTIVE_POLICY` candidates are fed through the same
`personal_expected_improvement` channel as `PERSONAL_EFFECT` today,
since Phase 10 has no separate adaptive channel yet. Full bandit-driven
action *selection* (choosing which candidates to offer at all) is
exposed as its own function (`app.personalization.bandit.select_action`)
for a future integration point, deliberately not forced through Phase
10's scoring path. Phase 13 never re-implements Phase 10's primary/
supporting selection.

## 16. Explainability

Fixed, phase-keyed strings only (`app.personalization.explain`) -- no
LLM, no dynamic generation:

| Phase | Explanation |
|---|---|
| `literature` | "Based on circadian research." |
| `personal_ranking` | "Based on your recent response history." |
| `personal_effect` | "Based on your personal response history to {type}." (or a comparative variant) |
| `adaptive_policy` | "Selected based on your recent response and current context." |

## 17. Limitations

- Every threshold (observation counts, weeks-active, blend weights,
  validity bounds, bandit priors) is a documented project engineering
  choice, not a statistically or clinically derived requirement.
- Phase 12's Phase 3 regression covariates are fixed to
  (`morning_light`, `meal_timing`, `exercise`); when the *target*
  intervention type is one of those three, its own compliance signal
  and its own covariate value are highly collinear, which can
  destabilize the recovered slope -- a real characteristic of Phase
  12's locked design, not something Phase 13 corrects. The Phase 13
  test suite deliberately validates recovery using `screen`
  (`evening_screen`) and `sleep` (`social_jetlag`) as target types,
  neither of which is a Phase 12 covariate.
- The bandit's reward-observation-noise variance is a fixed configured
  constant, not fit from data.
- `ADAPTIVE_POLICY` candidates reuse the `PERSONAL_EFFECT` expected-
  improvement channel into Phase 10 (see section 15) -- true
  context-conditioned action selection is not yet wired into the daily
  recommendation call.

## 18. Synthetic-data warning

`python -m app.scripts.run_personalization_diagnostics` builds its own
controlled synthetic participant histories and a fully simulated
bandit environment with known true reward means -- neither is real
participant data, and neither demonstrates real-world intervention
efficacy. They exist solely to verify the graduation logic and the
bandit's convergence/exploration behavior are wired correctly.

## Worked example: one participant transitioning through all phases

A participant starts a screen-reduction intervention (`intervention_type="screen"`)
on day 0, with cyclic compliance (`(day_index % 10) / 10`) and a known
synthetic effect of -10 min/compliance-unit, evaluated at several
checkpoints:

| Checkpoint | Observations | Weeks active | Phase |
|---|---|---|---|
| Day 7 | 7 | 1.0 | `literature` |
| Day 21 | 21 | 3.0 | `personal_ranking` |
| Day 42 | 42 | 6.0 | `personal_effect` |
| Day 63 | 63 | 9.0 | `personal_effect` |
| Day 91 | 90 | 13.0 | `adaptive_policy` |

(Reproduced exactly by `python -m app.scripts.run_personalization_diagnostics`.)
At day 42, `update_personalization_state` runs Phase 12's regression,
recovers a slope close to the injected -10.0, and upserts
`personal_effect_models` with `evidence_source="phase3_regression"`
and `model_version="1.0.0"`. From day 91 onward, the participant's
screen-reduction arm is eligible for Thompson-sampling-driven
selection alongside any other graduated intervention types, subject to
the exploration-dominance safeguard.
