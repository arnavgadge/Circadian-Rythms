# Research Handoff

This document orients a researcher continuing the work behind
CircadianIQ (release `v1.0.0-research-demo`, 2026-09-09). It is
written for someone with a research/ML background but no prior
exposure to this specific codebase.

## Current research question

Can behavioral and environmental proxies (sleep/wake timing, light
exposure, activity, meal timing, and similar observable signals)
estimate circadian phase (dim-light melatonin onset, DLMO) well
enough to usefully drive personalized behavioral interventions?

This question has, to date, been validated **only in a synthetic
simulation**, not against real human physiological data. That
boundary is load-bearing for how every result below should be read.

## Methodology

The overall approach:

1. A stateful synthetic-participant simulator (`app/synthetic/`)
   generates a population of synthetic participants with distinct
   chronotypes and behavioral personalities, each with a mechanistic
   DLMO state model (`app/synthetic/dlmo_state.py`) that produces a
   ground-truth DLMO trajectory alongside plausible behavioral
   observations.
2. Features are engineered from those behavioral observations only
   (never from the ground-truth DLMO) via `app/features/`.
3. An XGBoost model is trained to regress DLMO phase using a sin/cos
   circular-regression target encoding (`app/models/xgboost_model.py`,
   `app/models/target_encoding.py`), avoiding the discontinuity at the
   24-hour wraparound.
4. Validation is **subject-held-out**: no participant appearing in the
   test split has any of their windows in the training split
   (`app/models/splitting.py`) — this is the standard control against
   a model simply memorizing per-person idiosyncrasies rather than
   learning a generalizable phase-estimation function.
5. In production/demo use, the ML estimate is fused with an
   independent, non-ML mechanistic state-model estimate
   (`app/state/`, `app/fusion/`) rather than used alone.

For the full methodology writeup, see `docs/research_methodology.md`
(produced alongside this document as part of Phase 18 packaging — if
not yet present when you read this, it is expected imminently; until
then `docs/model_training_and_validation.md` and
`docs/synthetic_data_generation.md` are the authoritative sources).

## The validated experiment

The headline validated result, from the Phase 5 training run frozen
in `models/model_metadata_v1.json` and `release/results/`:

**93.73% of held-out synthetic test windows were within ±60 minutes**
(MAE 24.47 min).

Use this exact wording. Do not phrase this as human or clinical
accuracy — it is accuracy against a synthetic ground truth generated
by this project's own simulator, on a subject-held-out split of that
same simulator's output. See `release/results/model_metrics.csv`,
`release/results/baseline_comparison.csv`, and
`release/figures/` for the full metric set and diagnostic plots
underlying this number, all pulled directly from the original,
un-regenerated training run.

## Synthetic-data limitations

- No real human validation has been performed at any point. Every
  number in `release/results/` is synthetic-vs-synthetic.
- The synthetic assumptions (how light exposure, activity, and sleep
  timing map onto DLMO shift in `app/synthetic/dlmo_state.py`) are
  drawn from the circadian-biology literature at a level of
  simplification appropriate for a research demo, not a validated
  physiological model — they may not transfer to real individuals,
  particularly ones with irregular schedules, shift work, circadian
  disorders, or medication effects the simulator does not model.
- The generator's own behavioral-personality distributions
  (`app/synthetic/personalities.py`, `app/synthetic/population.py`)
  are **project choices**, not epidemiologically validated population
  parameters. They were chosen to produce a plausible and diverse
  synthetic population, not sampled from or fit to real cohort data.
- Because training, validation, and the fusion/alignment/contributor
  logic downstream of it were all developed and tuned against this
  same synthetic world, there is a systemic risk that the whole
  pipeline is well-calibrated to the simulator's own biases rather
  than to real circadian behavior.

## Assumptions needing future validation

See `docs/scientific_assumptions.md` (produced alongside this document
as part of Phase 18 packaging; if not yet present, see the per-subsystem
docs in `docs/` — `synthetic_data_generation.md`, `state_engine.md`,
`dlmo_fusion.md`, `alignment_engine.md` — for the assumptions as
currently documented inline in each subsystem).

## Future real-world dataset requirements

Establishing real-world validity would require a dataset with, at
minimum: repeated real DLMO measurements (lab or validated at-home
assay) per participant across enough days to fit a subject-held-out
split; concurrent behavioral/environmental logging comparable to what
this system's feature set expects (sleep/wake timing, light exposure,
activity, meal timing); enough participants and enough chronotype/
demographic diversity to test generalization rather than memorization;
and ideally a longitudinal intervention-compliance component to
validate the effectiveness/personalization layers, not just the phase
estimator. See `docs/research_methodology.md` (or the future real-data
path documentation produced alongside it) for the fuller treatment of
this — this section intentionally does not duplicate it at length.

## Potential next research steps

- An external validation cohort with real DLMO measurements, run
  through the existing feature pipeline unmodified, to test whether
  the 93.73%-within-±60min result transfers at all.
- Sensitivity analysis on the state model's bounds and rate parameters
  (`app/state/config.py`) — how much do the state-model's own
  free parameters drive the fused estimate versus the ML component.
- Ablation studies on feature groups (`app/features/feature_manifest.py`)
  to see which behavioral signal families the XGBoost model actually
  relies on, versus which were included by assumption.
- A more rigorous comparison of the stateful (mechanistic) estimator's
  standalone accuracy against the ML estimator's standalone accuracy,
  beyond their current combination in `app/fusion/` — useful both
  scientifically and for deciding whether the fusion weighting
  (`app/fusion/weights.py`) is doing what it's intended to do.
- Re-running the full synthetic experiment with alternative
  personality/population distributions to test how sensitive the
  headline number is to the generator's own project-chosen parameters
  (see "Synthetic-data limitations" above).
- Extending validation to the effectiveness/personalization layers
  (`app/effectiveness/`, `app/personalization/`), which currently have
  much less outcome-level validation than the phase estimator itself.

No external citations are asserted in this document beyond what is
already cited in the pre-existing per-subsystem docs under `docs/`;
do not add fabricated references when extending this document.
