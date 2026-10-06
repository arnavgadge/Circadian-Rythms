# CircadianIQ DLMO Fusion Layer (Phase 7)

## 1. Purpose

Combines CircadianIQ's two independent daily DLMO estimators -- the
Phase 5 XGBoost model and the Phase 6 state engine -- into one
authoritative fused DLMO, via the locked four-layer Q26 model:

```
XGBoost DLMO   ─┐
                 ├──►  FUSION LAYER  ──►  fused DLMO + confidence + disagreement + regime + diagnostics
State DLMO     ─┘
```

This module is pure computation (`app.fusion.fuse.fuse`): it never
queries the database and never imports the trained XGBoost model or
the state-engine transition logic. It receives two already-computed
hour values and combines them.

## 2. Inputs

```python
fuse(
    xgb_dlmo,              # float hour or None (Phase 5 estimate; None/NaN/Inf = unavailable)
    state_dlmo,            # float hour or None (Phase 6 estimate; None/NaN/Inf = unavailable)
    previous_fused_dlmo,   # float hour or None (yesterday's FUSED result -- see section 8)
    data_quality,          # DataQualityInput(tier, window_completeness, tier1_signals_missing, base_confidence=None)
    config=DEFAULT_FUSION_CONFIG,
)
```

## 3. Two-estimator architecture

XGBoost (behavioral-history pattern learner) and the state engine
(continuity-based mechanistic model) are structurally independent --
different inputs, different failure modes, different biases. Fusion
exists because neither estimator's weaknesses are assumed to dominate
the other's; combining them, weighted by how much they agree and how
much data-quality evidence supports each, is expected to be more
robust than either alone. This is a project design choice, not a
Kalman filter and not a claim about biological ground truth (see
section 14).

## 4. Base weight table (Layer 1, locked Q26 values)

| Data quality | XGBoost weight | State weight |
|---|---|---|
| HIGH | 0.65 | 0.35 |
| MODERATE | 0.55 | 0.45 |
| LOW | 0.40 | 0.60 |
| VERY_LOW | 0.20 | 0.80 |

These are project design parameters, not experimentally validated
biological constants. `app.fusion.config.FusionConfig.
base_weights_by_tier`.

## 5. Disagreement regimes (Layer 2)

Shortest circular absolute difference between `xgb_dlmo` and
`state_dlmo`, in minutes:

| Disagreement | Regime | Upper boundary is inclusive |
|---|---|---|
| ≤ 20 min | NORMAL | yes |
| ≤ 45 min | MODERATE | yes |
| ≤ 75 min | LARGE | yes |
| > 75 min | EXTREME | -- |

`app.fusion.weights.classify_disagreement` applies a `1e-6`-minute
tolerance at each boundary so upstream floating-point noise from
circular arithmetic (e.g. 23:50 to 00:10 computing as
`20.000000000000142` instead of exactly `20`) cannot flip a value that
is boundary-exact in intent into the wrong regime.

## 6. Weight adjustment (Layer 2, continued)

| Regime | XGB weight reduction | Resulting weights (from a 0.65/0.35 base) |
|---|---|---|
| NORMAL | 0 | 0.65 / 0.35 |
| MODERATE | −0.10 | 0.55 / 0.45 |
| LARGE | −0.20 | 0.45 / 0.55 |
| EXTREME | −0.30 | 0.35 / 0.65 |

`app.fusion.weights.adjust_weights`: `xgb_new = max(0, xgb_base -
reduction)`; `state_new = 1 - xgb_new`. The `max(0, ...)` clamp means a
reduction can never produce a negative weight -- e.g. VERY_LOW's base
XGB weight (0.20) minus an EXTREME reduction (0.30) clamps to exactly
`0.0`, with state taking the full remaining `1.0`, still normalized.

## 7. Circular fusion

Never average clock hours directly -- `(23.8 + 0.2) / 2 = 12.0` is
biologically meaningless for two estimates that are both near
midnight. `app.fusion.circular_fusion.circular_weighted_fusion`:

```
sin_xgb, cos_xgb     = clock_to_sincos(xgb_dlmo)
sin_state, cos_state = clock_to_sincos(state_dlmo)

x = w_xgb * cos_xgb + w_state * cos_state
y = w_xgb * sin_xgb + w_state * sin_state
r = sqrt(x^2 + y^2)

if r > 0: x, y = x/r, y/r
fused_hour = atan2(y, x) normalized to [0, 24)
```

Built entirely from primitives already established in Phases 4/5
(`app.features.time_encoding.clock_to_sincos`,
`app.models.target_encoding.sincos_to_clock`) -- not a third
reimplementation of sin/cos encoding.

**Worked example** (see section 12 for the full trace): `xgb_dlmo =
23:50`, `state_dlmo = 00:10`, HIGH data quality. Disagreement = 20
minutes exactly -> NORMAL regime -> weights stay at 0.65/0.35. The
fused result is **23:57**, correctly near midnight, never anywhere
near noon.

**Zero-magnitude edge case**: if the weighted vector's magnitude is
(numerically) zero -- which requires estimates exactly 12 hours apart
*and* equal effective weight, a combination the locked Q26 weight
table never actually produces on its own, since no base-weight/
regime-reduction combination yields exactly 0.5/0.5 -- the function
does **not** pick an arbitrary angle. It returns a documented fallback
(see section 11) and records why (`used_fallback`, `fallback_reason`).

## 8. Continuity constraint (Layer 3)

After circular fusion, the proposed fused value is compared against
**`previous_fused_dlmo`** -- never the previous XGBoost prediction
alone, the previous state prediction alone, or intrinsic DLMO -- using
the shortest signed circular difference. If that difference exceeds
the regime's cap, the result moves only the cap amount, in the same
signed direction, from the previous fused value.

| Disagreement regime | Continuity cap (minutes/day) |
|---|---|
| NORMAL | 60 |
| MODERATE | 45 |
| LARGE | 30 |
| EXTREME | 20 |

When fewer than two estimators are available (no disagreement regime
applies) or there is no previous fused value to compare against, a
default cap (`default_continuity_cap_minutes = 60`) is used instead --
a Phase 7 design choice, not a Q26-specified value.

This is fusion's **own** continuity rule, entirely separate from the
Phase 6 state engine's `adapted`/`current` bounds around intrinsic
DLMO -- those already exist one layer down (`app.state.engine`) and
are never re-implemented or re-checked here (see the project brief's
explicit "avoid duplicate biological constraints across layers").

**Worked continuity example**: `previous_fused_dlmo = 23:50`, proposed
`= 02:00` (a raw circular difference of about **+130 minutes**). Under
the NORMAL cap (60 min), the result is limited to **≈00:50** -- the
maximum allowed forward move from 23:50, not a naive/impossible jump to
02:00. A proposed move of exactly `+60` minutes (`23:50 -> 00:50`) is
accepted unchanged, since the boundary is inclusive.

## 9. Confidence penalty (Layer 4)

| Disagreement regime | Confidence penalty |
|---|---|
| NORMAL | 0 |
| MODERATE | −8 |
| LARGE | −18 |
| EXTREME | −30 |

Applied to a **base confidence** (0-100) and clamped back to `[0,
100]`. This phase does not invent a competing confidence model: the
brief's own Q25 confidence-label thresholds are reused unchanged
(`app.fusion.config.FusionConfig.confidence_label_thresholds =
(80, 60, 40)`, giving HIGH / MODERATE / LOW / NO_PREDICTION). The
*base* confidence score itself, however, has no earlier-phase
implementation to reuse -- no prior phase computes a numeric 0-100
confidence from a data-quality tier -- so `app.fusion.config.
FusionConfig.base_confidence_by_tier` supplies a plain, clearly-labeled
default (HIGH→90, MODERATE→70, LOW→50, VERY_LOW→20) that `fuse()` uses
only when the caller doesn't supply `data_quality.base_confidence`
directly. A later phase that builds a real data-quality-to-confidence
system can pass its own value straight through without touching the
fusion algorithm.

## 10. No-prediction conditions

`app.fusion.confidence.should_suppress_prediction` sets
`prediction_made = False` whenever **any** of:

- all critical Tier-1 inputs are missing (`tier1_signals_missing`), or
- window completeness is below 50%, or
- final confidence (after the Layer-4 penalty) is below 40,

**regardless of whether a fused value was mathematically computable.**
A mathematically available estimate is not automatically an acceptable
user-facing prediction -- `fused_final` may still hold a computed
value (kept for research/debugging transparency), but `prediction_made
= False` tells the caller not to surface it normally.

When confidence is LOW (40-59) but not suppressed, `is_approximate =
True` -- signaling that a later UI layer should render something like
"~1:45 AM" rather than false precision. No UI text is hard-coded here;
this module only returns the structured flag.

## 11. Estimator fallback behavior

Model **availability** (did an estimator return a valid result) is
tracked separately from data **quality** (how good the input evidence
was) -- `FusionResult.xgb_available`/`state_available` vs.
`data_quality.tier`/`window_completeness`. They are never collapsed
into one boolean.

| Situation | Weights | Confidence | Disagreement |
|---|---|---|---|
| Both available | Normal 4-layer pipeline | Normal 4-layer pipeline | Computed, regime classified |
| XGB unavailable | state = 1.0, xgb = 0.0 | `single_estimator_confidence_penalty` (−15) applied | Not applicable (`None`) |
| State unavailable | xgb = 1.0, state = 0.0 | Same penalty applied | Not applicable (`None`) |
| Both unavailable | n/a | 0 | Not applicable |
| Zero-magnitude circular vector | n/a | -- | -- |

Both-unavailable and zero-magnitude cases use the same documented
fallback order: **previous fused DLMO**, then **state estimate**, then
**XGBoost estimate**, then no prediction at all -- never a randomly
chosen angle.

## 12. Edge cases (all verified by `tests/test_fusion_*.py`)

| Case | Result |
|---|---|
| XGB=23:50, State=00:10 (20 min, NORMAL) | Fused ≈ 23:57, near midnight |
| XGB=00:10, State=23:50 (reversed) | Symmetric under equal weights; still near midnight |
| XGB=12:00, State=12:30 | Fused ≈ 12:13, near noon (correctly, since both inputs *are* near noon) |
| XGB=06:00, State=18:00 (12h apart) | Weighted (not equal) under the locked table -> a real fused point; only exactly-equal-weight 12h-apart inputs hit the documented zero-magnitude fallback |
| Disagreement exactly 20 / 45 / 75 min | Classified NORMAL / MODERATE / LARGE (inclusive), not the next regime up |
| previous=23:50, proposed=00:50 (+60 min, NORMAL cap) | Accepted unchanged (boundary inclusive) |
| previous=23:50, proposed=02:00 (+130 min, NORMAL cap) | Limited to ≈00:50 |
| NaN or infinite estimate | Treated as unavailable, not propagated |

## 13. Diagnostics

Every `FusionResult` exposes (not necessarily all persisted to SQL):
`xgb_dlmo`, `state_dlmo`, `previous_fused_dlmo`, `xgb_available`,
`state_available`, `fused_before_continuity`, `fused_final`,
`xgb_base_weight`, `state_base_weight`, `xgb_final_weight`,
`state_final_weight`, `disagreement_minutes`, `disagreement_regime`,
`continuity_cap_minutes`, `continuity_applied`,
`continuity_adjustment_minutes`, `base_confidence`,
`confidence_penalty`, `final_confidence`, `confidence_label`,
`prediction_made`, `is_approximate`, `used_fallback`,
`fallback_reason`.

### Diagnostic experiment (`python -m app.scripts.run_fusion_diagnostics`)

Run once, on the Phase 5 held-out test participants (200 participants,
4,800 windows), using the trained XGBoost model's predictions and the
Phase 6 state engine's replayed estimates. **No fusion parameter was
tuned against this test set** -- the Q26 weights/thresholds/caps are
fixed configuration, applied here, never adjusted based on the result.

| Metric | Value |
|---|---|
| Windows | 4,800 |
| Mean XGB final weight | 0.584 |
| Mean state final weight | 0.416 |
| Continuity caps applied | 61 |
| Disagreement regimes | normal 2,427 / moderate 1,702 / large 530 / extreme 141 |
| Confidence labels | high 4,129 / moderate 671 |
| XGBoost MAE (vs. synthetic ground truth) | 24.47 min |
| Fused MAE | 12.89 min |
| Apparent improvement | 11.58 min |

**Read this table together with section 14.** The apparent 11.58-minute
improvement is expected and mechanical, not evidence that fusion
improves real-world accuracy -- see below.

## 14. Scientific limitations

- **This is not a Kalman filter.** It may be described as an
  interpretable state-and-model fusion mechanism, or loosely as
  "Kalman-filter-inspired" *only* as an analogy (weighted combination
  of two estimates, adjusted by their disagreement) -- there is no
  process/observation noise model, no covariance propagation, and no
  optimality claim.
- **The state model is not "true biology."** It is CircadianIQ's own
  synthetic modeling framework (see `docs/state_engine.md`), and
  fusion does not elevate its status.
- **The diagnostic experiment's apparent improvement is inflated by
  construction, not a real accuracy claim.** In the Phase 3 synthetic
  dataset, the "state estimate" used here is recomputed by replaying
  the *exact same* state-transition model Phase 3 used to generate the
  ground-truth target in the first place -- so, for this dataset, the
  state estimate **is** the ground truth. Fusing an estimator that is
  the answer key with an imperfect one (XGBoost) will always look like
  an improvement, mechanically, regardless of whether the underlying
  fusion idea has any real-world merit. What this experiment actually
  demonstrates is that the fusion **mechanics** work as designed (base
  weights, disagreement classification, continuity capping, confidence
  penalties) -- not that fusion improves DLMO accuracy on independently
  measured, real human data. Read the reported "improvement" as a
  mechanism check, not an accuracy result.
- **Every numeric parameter (base weights, thresholds, caps,
  penalties) is a locked project design choice (Q26)**, not a fitted
  or experimentally validated constant. No claim of biological
  validation is made anywhere in this module or its configuration.
- **The Phase-7-introduced `base_confidence_by_tier` mapping and
  `single_estimator_confidence_penalty` value** are Phase 7's own
  defaults, filling a gap no earlier phase addressed -- not something
  handed down from an established "Q25 confidence model" (only the
  *label thresholds* were actually locked previously).

## Module map

```
app/fusion/
    config.py             FusionConfig: all Q26 parameters, versioned (v1.0.0)
    weights.py              FusionWeights, get_base_weights, classify_disagreement, adjust_weights
    circular_fusion.py       circular_weighted_fusion (+ documented zero-magnitude fallback)
    continuity.py             apply_continuity_cap
    confidence.py              DataQualityInput, get_base_confidence, apply_confidence_penalty,
                                confidence_label, should_suppress_prediction
    fuse.py                     FusionResult, fuse() -- the single entry point
    diagnostics.py               run_fusion_over_windows, summarize_fusion_report, plots

app/scripts/run_fusion_diagnostics.py   CLI entry point
```
