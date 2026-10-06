# Discussion (Draft)

**Status: draft.** This document is a methodology/results draft toward an eventual IEEE-style paper; it is not a finished or submitted manuscript.

**Release version:** v1.0.0-research-demo. **Phase 17 audit status:** CONDITIONAL PASS.

> As throughout this draft: every interpretive claim below is scoped strictly to CircadianIQ's synthetic system and synthetic evaluation. Nothing here should be read as a claim about real human circadian physiology or real-world estimation accuracy.

---

## 1. Learned Model vs. Non-Learned Baselines

On the held-out synthetic test set, the XGBoost model substantially outperforms both non-learned baselines evaluated on the identical data (MAE 24.47 min vs. 57.2 min for a participant-mean baseline and 342.1 min for an MSFsc-proxy baseline; see `results_draft.md` §4). This gap is informative about the *pipeline*, not about human circadian biology: it indicates that the six-day behavioral feature window carries substantially more predictive signal, within this synthetic world, than either a static per-participant average or a proxy built from sleep midpoint alone. The MSFsc-proxy baseline's near-total failure (0.0% within ±60 min) is expected by construction, since MSFsc measures sleep midpoint rather than DLMO and the synthetic generator embeds a structural multi-hour offset between the two quantities that a non-learned proxy has no way to correct for. That the learned model closes most of this gap indicates the model successfully extracts the relationship the generator encodes between behavior and DLMO — again, a statement about pipeline correctness on synthetic data, not an independent accuracy claim.

## 2. Feature Importance as a Sanity Check, Not a Discovery

Feature-importance analysis (`release/results/feature_importance.csv`, `release/results/shap_importance.csv`, `release/figures/07_feature_importance.png`) shows evening screen timing and meal timing among the most influential features to the model's predictions. This is directionally consistent with how the synthetic data generator itself was constructed: the generator's behavioral-effect model explicitly scales a participant's DLMO shift by evening screen exposure and last-meal timing (among other signals), weighted by that participant's own sensitivity multipliers (see `methodology_draft.md` §1–§2). Recovering this relationship in the trained model is therefore best understood as a **sanity check that the modeling pipeline correctly learns the relationships the generator encodes**, not as an independent scientific finding about which real-world behaviors most influence human circadian phase. Because the generator and the predictor share a common synthetic world, agreement between "what the generator encodes" and "what the model learns" is closer to an internal-consistency check than external validation.

## 3. Stratified Performance by Chronotype and Personality

Performance varies somewhat across chronotype and personality strata (`release/results/chronotype_metrics.csv`, `release/results/personality_metrics.csv`; `release/figures/05_performance_by_chronotype.png`, `release/figures/06_performance_by_personality.png`). We interpret this variation cautiously: differences across strata plausibly correlate with how strongly each stratum is represented in the training population (e.g., the Intermediate chronotype makes up 59% of generated participants versus 14% for Late chronotype), rather than reflecting some strata being intrinsically harder to estimate in a way that would generalize beyond this dataset's own generation parameters. Disentangling "underrepresented in training data" from "structurally harder to estimate" would require either a rebalanced synthetic dataset or, more importantly, real-world data with an independently known stratum distribution — neither of which this draft has.

## 4. On the Fusion Diagnostic

As detailed in `results_draft.md` §5, the fusion diagnostic's substantially lower MAE (12.89 min vs. 24.47 min) is an artifact of the synthetic evaluation setup rather than a demonstration that fusing a learned estimator with an independent mechanistic estimator improves real-world accuracy: the state-engine estimator used in this diagnostic replays the same transition model that produced the ground-truth labels. We surface this number for transparency and because it does validate that the fusion layer's weighting and disagreement-handling logic behaves as intended, but we are explicit that it must not be cited, in isolation, as evidence of fusion's real-world value.

## 5. Overall Interpretation

Taken together, these results support a modest and specific claim: the CircadianIQ pipeline — synthetic data generation, feature engineering, model training, fusion, alignment, and downstream recommendation/personalization/safety layers — is internally consistent and functions as designed against its own synthetic ground truth, and a system-wide adversarial audit (Phase 17) found the architecture sound enough to reach a status of CONDITIONAL PASS with three specific, documented gaps left open. This is a necessary but not sufficient step toward a system that could ever be evaluated against real human circadian phase; that evaluation has not been attempted in this work and remains the highest-priority next step (see `future_work_draft.md`).
