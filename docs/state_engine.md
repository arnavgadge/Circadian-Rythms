# CircadianIQ State Engine (Phase 6)

## 1. Purpose

Implements the stateful, three-layer circadian phase model
(`intrinsic -> adapted -> current DLMO`) as a single, authoritative,
XGBoost-independent computation library. It represents the evolving
biological state from behavioral history alone -- a second, independent
DLMO estimator alongside the Phase 5 XGBoost model. **Fusing the two is
explicitly out of scope for this phase** (Phase 7).

This phase is as much a **refactor** as a new feature: Phase 3's
synthetic generator originally implemented this same three-layer
transition and its behavioral-effect model directly inside
`app.synthetic.dlmo_state`. That logic has been promoted to `app.state`
as the one shared implementation; `app.synthetic.dlmo_state` is now a
thin backward-compatible translation layer over it (see section 13).
There is no `synthetic_state_model.py` / `production_state_model.py`
split -- there is one engine.

## 2. Three-layer state architecture

```
intrinsic_DLMO   (fixed biological anchor)
     |
adapted_DLMO     (slow behavioral equilibrium, bounded around intrinsic)
     |
current_DLMO     (fast day-to-day estimate, pulled toward adapted, bounded around intrinsic)
```

Module map:

```
app/state/
    config.py             StateEngineConfig -- every numeric parameter, versioned
    circadian_state.py     CircadianState, ParticipantPhaseTraits, StateTransitionDebug
    behavioral_effect.py    the shared light/screen/meal/exercise/caffeine effect model
    engine.py               initialize_state(_stochastic), step, step_stochastic
    replay.py                replay_trajectory -- full-history reconstruction
    sanity.py                the 10 automated state sanity checks
    db_adapter.py            read-side Phase 2 schema <-> engine-type translation
    diagnostics.py           the 6 required diagnostic plot categories
```

## 3. Intrinsic DLMO

The participant's stable biological predisposition. Set once at
onboarding (`CircadianState.intrinsic_dlmo_hour`), associated with the
chronotype category shown to the user, and **never** modified by
`step()` -- every state update explicitly carries the previous
`intrinsic_dlmo_hour` forward unchanged. Verified automatically
(`app.state.sanity.validate_trajectory`, check "intrinsic_never_changes").

## 4. Adapted DLMO

The slowly-changing behavioral equilibrium. Moves a small fraction of
the way toward the direction today's behavior implies
(`adaptation_rate`, ~1%/day) and a smaller fraction back toward
intrinsic (`intrinsic_recovery_rate`, ~0.5%/day), then is clamped to
stay within `adapted_max_offset_hours` (~2h) of intrinsic.

## 5. Current DLMO

The dynamic daily estimate. Moves by today's full behavioral shift,
plus a pull toward adapted DLMO (`current_pull_rate`, ~50% of the
adapted-current gap closed per day), then is clamped to stay within
`current_max_offset_hours` (~3h) of intrinsic, and -- new in this
phase -- a final `daily_continuity_cap_minutes` safety clamp on the
*total* day-over-day change (see section 8).

## 6. Equations

Let `h` denote an hour value and `circdiff(a, b)` the shortest signed
circular difference `a - b` (see section 10). For day `t`, given the
previous state (`intrinsic`, `adapted_{t-1}`, `current_{t-1}`) and
today's behavioral effect total `shift_t` (minutes, from
`app.state.behavioral_effect.compute_behavioral_effect`, converted to
hours):

**Adapted DLMO** (computed first):

```
behavioral_equilibrium_t = adapted_{t-1} + shift_t / 60          (an hour value)

adapted_t = adapted_{t-1}
            + adaptation_rate        * circdiff(behavioral_equilibrium_t, adapted_{t-1})
            + intrinsic_recovery_rate * circdiff(intrinsic, adapted_{t-1})

adapted_t = clip_to_bound(adapted_t, intrinsic, adapted_max_offset_hours)
```

Because `circdiff(x + d, x) == d`, this is algebraically identical to
"nudge adapted by `adaptation_rate * shift_t/60` plus the intrinsic
pull" -- the `behavioral_equilibrium` framing is a naming choice for
interpretability, not a different formula (see section 13).

**Current DLMO** (computed second, using the *previous* day's adapted
value -- see section 11 for why):

```
pull_to_adapted_t = current_pull_rate * circdiff(adapted_{t-1}, current_{t-1})

current_t = current_{t-1} + shift_t / 60 + pull_to_adapted_t + state_noise_t

current_t = apply_continuity_cap(current_t, current_{t-1})   (see section 8; skippable)
current_t = clip_to_bound(current_t, intrinsic, current_max_offset_hours)
```

`state_noise_t` is `0.0` unless the caller explicitly used the
stochastic entry point (section 9).

## 7. Parameter meanings

| Parameter | Meaning | Default |
|---|---|---|
| `adaptation_rate` | Fraction of the gap to today's behavioral equilibrium that adapted closes per day | 0.01 |
| `intrinsic_recovery_rate` | Fraction of the gap back to intrinsic that adapted closes per day | 0.005 |
| `adapted_max_offset_hours` | Max allowed distance of adapted from intrinsic | 2.0h |
| `current_pull_rate` | Fraction of the adapted-current gap that current closes per day | 0.5 |
| `current_max_offset_hours` | Max allowed distance of current from intrinsic | 3.0h |
| `daily_continuity_cap_minutes` | Final cap on total day-over-day current-DLMO change | 60 min |
| `initialization_offset_hours` | Deterministic onboarding offset (adapted/current from intrinsic) | 0.0h |
| `initialization_offset_sd_hours` | SD of the *stochastic* onboarding nudge | 0.10h |
| `daily_state_noise_sd_minutes` | SD of the *stochastic* daily current-DLMO noise term | 5 min |

All defaults live in `app.state.config.StateEngineConfig`
(`state_config_version = "1.0.0"`) -- never as bare literals in
`engine.py` or `behavioral_effect.py`.

## 8. Bounds and the continuity cap

Two *bound* constraints (adapted/current distance from intrinsic) exist
because Phase 3 already needed them for a stable 30-day simulation. The
`daily_continuity_cap_minutes` cap is **new in this phase**: it bounds
the *total* day-over-day change in current DLMO (behavioral shift +
pull-to-adapted + noise combined), independent of the two distance
bounds -- catching a pathological single-day jump a numerical bug,
incorrect circular arithmetic, or an extreme input could otherwise
produce. It is a synthetic simulation-stability constraint, not a
physiological ceiling, and it defaults to **enabled** for new state-engine
use but is explicitly **disabled** when replaying Phase 3 trajectories
(section 13). The finer-grained, disagreement-specific caps mentioned
in the project's fusion design belong to Phase 7 and are not
implemented here.

## 9. Circular-time handling

Every arithmetic operation that combines two clock-time-like quantities
goes through `app.synthetic.time_utils.circular_diff_hours` /
`normalize_hour` -- never a bare subtraction. `23:50 -> 00:10` is +/-20
minutes, never ~23h40m (verified directly, both in
`app.state.sanity.validate_trajectory`'s "midnight_circular_arithmetic_correct"
check and in `tests/test_state_engine.py`). Internally, updates are
computed as an hour offset added to a previous hour value and then
`normalize_hour`-wrapped back into `[0, 24)`; no code path in this
package ever compares two raw hour floats with `<`/`>` to reason about
which is "later".

## 10. Determinism vs. stochasticity

`step()` is deterministic: `noise_minutes` and `state_noise_hours`
default to `0.0` and are never drawn internally. `step_stochastic()` is
the **only** function in `app.state` that touches a random generator --
it draws both noise terms from a caller-supplied
`numpy.random.Generator` and then calls `step()` with the drawn values,
visibly. The same separation applies to initialization
(`initialize_state` vs. `initialize_state_stochastic`). Production
inference (Phase 7+) should only ever call the deterministic entry
points.

## 11. Temporal ordering

For day `t`: adapted is computed first, then current -- but current's
pull-toward-adapted term deliberately reads the **previous** day's
adapted value (`adapted_{t-1}`), not the one just computed in the same
call. Pulling current toward a value that only becomes known partway
through today's own update would be a same-day circular dependency
with no clear meaning ("pull toward where you're about to move to
today"). This ordering is identical everywhere the engine is used
(Phase 3's simulator and this phase's replay function share the exact
same `step()` call), so there is no risk of the simulator and a future
inference path disagreeing about which day's adapted value current is
pulled toward.

## 12. Synthetic-assumption disclaimer

**Every equation and parameter in this document is CircadianIQ's own
synthetic modeling framework, not a validated physiological model of
human circadian regulation.** No project source claims these specific
adaptation rates, pull rates, or bounds are drawn from measured human
data -- they are the same synthetic design choices already used (under
different names) by the Phase 3 generator, now centralized. This
mirrors the source-backed-vs-synthetic distinction established in
`docs/synthetic_data_generation.md`; the behavioral-effect curve
anchors this engine reuses (imported directly from
`app.synthetic.config`, never re-derived) retain whatever citation
labeling they already had there.

## 13. Relationship to Phase 3

`app.synthetic.dlmo_state` (originally Phase 3's own implementation) is
now a translation layer: it builds `DailyBehaviorInputs`/
`ParticipantPhaseTraits` from Phase 3's `DailyBehaviorRecord`/
`ParticipantTraits`, calls `app.state.engine.step`, and translates the
result back into Phase 3's original `DLMOState`/`DailyEffectBreakdown`
shapes -- so `app.synthetic.simulator` and every existing Phase 3 test
work unchanged. Two details matter for exact reproduction of
historical synthetic data:

1. **The continuity cap is disabled** (`apply_continuity_cap=False`)
   in this compatibility path, since it did not exist when the
   historical dataset was generated.
2. **The random-draw order is preserved exactly** (behavioral noise
   drawn first, then state noise), so a seeded Phase 3 run reproduces
   bit-for-bit.

Verified empirically: regenerating the full 1,000-participant, seed-42
dataset after this refactor and comparing against the values already
stored in `circadian_labels` from before the refactor showed
differences on the order of 1e-5 hours (i.e. sub-second), attributable
entirely to the database's second-level time rounding, not to any
computational drift. `tests/test_state_replay.py::
test_shared_engine_reproduces_phase3_generator_trajectory_when_noise_free`
additionally proves exact (`1e-9` tolerance) equivalence under a
noise-free configuration, isolating the state-transition math itself
from any stochastic-replay ambiguity.

## 14. Relationship to future XGBoost fusion

This engine produces one candidate `current_DLMO` estimate per day,
computed purely from state continuity and behavioral history -- with
**no dependency on the trained XGBoost model** (verified by
`tests/test_state_engine.py::test_state_package_has_no_xgboost_dependency`,
which scans every module in `app.state` for any `xgboost`/`app.models`
reference). Phase 5's XGBoost model produces an independent estimate
from the same underlying behavioral signals via a completely different
mechanism (a learned tree ensemble over the Phase 4 feature window).
Phase 7 will combine the two, weighted by data quality, with a
disagreement adjustment, a biological continuity constraint, and a
confidence penalty -- none of which exists yet. Today, both estimators
can be computed side by side, but nothing in this codebase merges them.

## 15. Limitations

- **The continuity-cap/replay tradeoff** (section 8, 13) means the
  Phase-6-introduced safety cap is inactive on the historical Phase 3
  dataset; it only protects new (post-Phase-6) state-engine use.
- **`behavioral_equilibrium` is algebraically equivalent to Phase 3's
  original formula**, not a materially new dynamic -- it is a naming/
  interpretability improvement, not a scientific refinement.
- **No physiology input.** Consistent with the Version-1 architecture
  lock (Phase 4/5), the state engine's behavioral-effect model never
  reads `physiology_logs`.
- **The state engine does not write to the database.** Only read-side
  adapters exist (`app.state.db_adapter`); producing an authoritative
  `circadian_labels` row from a state-engine estimate is Phase 7's
  responsibility, once fusion exists to decide how it combines with
  XGBoost's estimate.
- **Sensitivity multipliers and `baseline_sleep_onset_hour`** are not
  columns on `participant_profiles` -- a caller reading real database
  state must supply them from wherever they are actually recorded
  (Phase 3's `synthetic_personality_profile` JSON blob, for the
  existing synthetic dataset); `app.state.db_adapter` does not invent
  defaults for them.
