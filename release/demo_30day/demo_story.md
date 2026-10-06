# 30-Day Demo Story: Arjun -- CircadianIQ Demo User


**This is a deterministic synthetic demonstration participant (participant_id=9001), not a sampled population participant and not a real individual.** Every value below is a real, unmodified output of the CircadianIQ pipeline (feature engineering -> XGBoost -> state engine -> fusion -> alignment -> contributors -> recommendation -> compliance -> personalization) given a predefined, hand-designed 30-day behavioral schedule (`demo/scenarios/late_screen_recovery_30d.yaml`). Nothing in this report was hard-coded or manually adjusted after the fact -- see `docs/30_day_demo_scenario.md` for the full design rationale, including two schedule retunings made *before* accepting this final run, each driven by inspecting real pipeline output rather than the desired narrative.


## Persona


Chronotype: **Late**. Behavioral personality: screen-heavy user with a mild social jetlag pattern. This is a deliberately-designed persona for demonstration purposes, not drawn from the synthetic population generator.


## Days 1-7 -- Baseline


A consistently late, screen-heavy routine: sleep onset around 1:45-2:00 AM, evening screens until 1:15-1:30 AM, weak/late morning light, a late last meal, and moderate social jetlag. Held stable (small deterministic variation only, never random) so the system has a coherent 6-day window once prediction begins on day 7.


### CHECKPOINT_DAY_7 (2026-04-12, stage STAGE_1_BASELINE)

- Estimated biological clock (fused DLMO): **23:47:04**
- Alignment score: **68.3/100**
  - Components: sleep_consistency=88, morning_light=25, evening_screen=10, meal_timing=30, social_jetlag=40
- Top contributors: #1 evening_screen (hurting), #2 social_jetlag (hurting), #3 meal_timing (hurting)
- Confidence: low
- Recommendation: Try stopping screens by 10:45 PM.
- Compliance: 1.00
- Personalization phase: literature


## Days 8-10 -- System Identifies the Problem


The baseline pattern continues while the system, now with a full trailing history, ranks contributors and issues a graduated recommendation targeting the dominant contributor.


### CHECKPOINT_DAY_10 (2026-04-15, stage STAGE_2_IDENTIFY)

- Estimated biological clock (fused DLMO): **00:23:08**
- Alignment score: **55.6/100**
  - Components: sleep_consistency=88, morning_light=25, evening_screen=10, meal_timing=30, social_jetlag=40
- Top contributors: #1 evening_screen (neutral), #2 social_jetlag (hurting), #3 meal_timing (neutral)
- Confidence: moderate
- Recommendation: Try stopping screens by 10:33 PM.
- Compliance: 0.32
- Personalization phase: literature


## Days 11-18 -- Behavioral Change


A deliberate, gradual improvement in screen cutoff and morning light timing, with partial compliance early and stronger compliance later. The magnitude of this change was tuned (see docs/30_day_demo_scenario.md) to a pace the real state engine can actually track within the story's 30-day span, after an initial, more aggressive draft was found to overshoot the model's own adaptation speed.


### CHECKPOINT_DAY_18 (2026-04-23, stage STAGE_3_CHANGE)

- Estimated biological clock (fused DLMO): **00:02:58**
- Alignment score: **54.6/100**
  - Components: sleep_consistency=81, morning_light=55, evening_screen=60, meal_timing=30, social_jetlag=48
- Top contributors: #1 evening_screen (neutral), #2 meal_timing (neutral), #3 social_jetlag (hurting)
- Confidence: moderate
- Recommendation: Try stopping screens by 10:48 PM.
- Compliance: 0.48
- Personalization phase: literature


## Days 19-24 -- Biological Response


Continued behavioral improvement. The estimated biological clock and alignment score here are entirely the real state engine's and fusion layer's own output -- never overwritten by this demo.


### CHECKPOINT_DAY_24 (2026-04-29, stage STAGE_4_RESPONSE)

- Estimated biological clock (fused DLMO): **23:45:49**
- Alignment score: **64.7/100**
  - Components: sleep_consistency=96, morning_light=100, evening_screen=85, meal_timing=30, social_jetlag=59
- Top contributors: #1 meal_timing (neutral), #2 morning_light (hurting), #3 evening_screen (neutral)
- Confidence: moderate
- Recommendation: Try finishing your last meal by 10:08 PM.
- Compliance: 1.00
- Personalization phase: literature


## Days 25-30 -- Stable Improvement


Behavior stabilizes at a substantially, but not perfectly, improved routine.


### CHECKPOINT_DAY_30 (2026-05-05, stage STAGE_5_STABLE)

- Estimated biological clock (fused DLMO): **23:36:24**
- Alignment score: **68.9/100**
  - Components: sleep_consistency=95, morning_light=100, evening_screen=100, meal_timing=55, social_jetlag=69
- Top contributors: #1 meal_timing (neutral), #2 morning_light (hurting), #3 social_jetlag (hurting)
- Confidence: moderate
- Recommendation: Try finishing your last meal by 9:56 PM.
- Compliance: 1.00
- Personalization phase: literature


## Summary


- Mean alignment, days 1-10 (baseline/identify): **63.7**

- Mean alignment, days 25-30 (stable): **67.7**

- Personalization for both the `screen` and `meal` intervention types stayed at the `literature` phase for the full 30 days. This is a genuine, inspected outcome, not a shortfall to paper over: the recommendation engine's own contributor-driven target legitimately shifted from screen to meal around day 19-20 (see the contributor transition figure), splitting the 23 days of compliance evidence across two intervention types before either individually reached the 3-weeks-active graduation threshold (`app/personalization/config.py:ranking_min_weeks_active`). Per the brief's own guidance, the honest report here is: **personalization is still learning from this participant's history.**

- All figures: `release/demo_30day/figures/`. Full daily data: `release/demo_30day/daily_summary.csv`. Machine-readable summary: `release/demo_30day/journey_summary.json`.

- Every number above is an **observed, synthetic** output -- never a proven causal effect and never a clinical measurement.