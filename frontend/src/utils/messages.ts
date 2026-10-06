/**
 * Fixed, pre-approved user-facing copy. Nothing here is generated
 * dynamically -- every string is chosen ahead of time and only
 * selected based on structured API fields (confidence label, safety
 * severity, etc.), matching the wording specified in the product
 * boundary (see docs/ui_architecture.md "Terminology").
 */

import type { ConfidenceLabel } from "../api/types";

export const QUALIFIER_TEXT: Partial<Record<ConfidenceLabel, string>> = {
  moderate: "Estimated from partial data.",
  low: "Approximate estimate — complete more data for better accuracy.",
};

export const BOUNDARY_NOTE_FULL =
  "CircadianIQ estimates your circadian phase from behavioral patterns. It is not a medical device, does not perform laboratory measurements, and does not diagnose any condition.";

export const NON_DIAGNOSTIC_STATEMENT = "This is not a diagnosis.";

export const HIGH_SEVERITY_HEADLINE = "Your recent pattern may benefit from professional evaluation.";
export const HIGH_SEVERITY_BODY = "CircadianIQ cannot diagnose circadian rhythm disorders.";

export const NO_PREDICTION_HEADLINE = "Today's biological-clock estimate is unavailable.";
export const NO_PREDICTION_BODY = "Not enough reliable data was available.";

export const INFERENCE_LOADING_TEXT = "Updating your circadian profile…";

export const CAUSAL_CAVEAT = "Other behaviors also changed during this period.";
