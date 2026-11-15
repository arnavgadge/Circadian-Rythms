/**
 * Fixed, consumer-facing label lookups. No natural-language is
 * generated here -- every string is a static mapping from a
 * structured API value to already-approved wording (see
 * docs/ui_architecture.md "Terminology"). Never expose internal
 * jargon like "Thompson sampling," "posterior," or "personal effect
 * slope" in the consumer view.
 */

import type { ConfidenceLabel, SafetySeverity } from "../api/types";

export const PERSONALIZATION_LABELS: Record<string, string> = {
  literature: "Based on research",
  personal_ranking: "Based on your recent response history",
  personal_effect: "Personalized estimate",
  adaptive_policy: "Increasingly personalized to you",
};

export function personalizationLabel(phase: string | null | undefined): string {
  if (!phase) return "Based on research";
  return PERSONALIZATION_LABELS[phase] ?? "Based on research";
}

export const EXPECTED_IMPROVEMENT_SOURCE_LABELS: Record<string, string> = {
  literature: "Based on research",
  personal: "Based on your history",
  blended: "Blended estimate",
};

export function expectedImprovementSourceLabel(source: string | null | undefined): string | null {
  if (!source) return null;
  return EXPECTED_IMPROVEMENT_SOURCE_LABELS[source] ?? null;
}

export const CONTRIBUTOR_SIGNAL_LABELS: Record<string, string> = {
  evening_screen: "Evening screens",
  morning_light: "Morning light",
  meal_timing: "Meal timing",
  exercise: "Exercise timing",
  social_jetlag: "Social jetlag",
};

export function contributorLabel(signal: string): string {
  return CONTRIBUTOR_SIGNAL_LABELS[signal] ?? signal.replace(/_/g, " ");
}

export const DIRECTION_LABELS: Record<string, string> = {
  hurting: "Working against your alignment",
  opportunity_missed: "An opportunity to help more",
  neutral: "Currently neutral",
};

export function directionLabel(direction: string | null): string | null {
  if (!direction) return null;
  return DIRECTION_LABELS[direction] ?? direction;
}

export const CONFIDENCE_LABELS: Record<ConfidenceLabel, string> = {
  high: "High",
  moderate: "Moderate",
  low: "Low",
  no_prediction: "Unavailable",
};

export function confidenceLabel(label: ConfidenceLabel | null): string {
  if (!label) return "Unavailable";
  return CONFIDENCE_LABELS[label] ?? label;
}

export const SEVERITY_LABELS: Record<SafetySeverity, string> = {
  MODERATE: "Pattern note",
  HIGH: "Safety note",
};

export const ALIGNMENT_COMPONENT_LABELS: Record<string, string> = {
  sleep_consistency: "Sleep consistency",
  morning_light: "Morning light",
  evening_screen: "Evening screen",
  meal_timing: "Meal timing",
  social_jetlag: "Social jetlag",
};

export const FLAG_TYPE_LABELS: Record<string, string> = {
  persistent_late_phase: "Consistently late estimated clock",
  persistent_early_phase: "Consistently early estimated clock",
  continuous_dlmo_drift: "Continuous drift in your estimated clock",
  low_alignment_despite_compliance: "Low alignment despite consistent effort",
};

export function flagTypeLabel(flagType: string): string {
  return FLAG_TYPE_LABELS[flagType] ?? flagType.replace(/_/g, " ");
}

/** Short, non-causal labels for the contributor direction pill. */
export const DIRECTION_SHORT_LABELS: Record<string, string> = {
  hurting: "Working against",
  opportunity_missed: "Missed opportunity",
  neutral: "Neutral",
};

export function directionShortLabel(direction: string | null): string | null {
  if (!direction) return null;
  return DIRECTION_SHORT_LABELS[direction] ?? direction.replace(/_/g, " ");
}

export const INTERVENTION_TYPE_LABELS: Record<string, string> = {
  light: "Morning light",
  screen: "Screen cutoff",
  sleep: "Sleep timing",
  meal: "Meal timing",
  exercise: "Exercise timing",
  caffeine: "Caffeine timing",
};

export function interventionTypeLabel(type: string | null | undefined): string {
  if (!type) return "Intervention";
  return INTERVENTION_TYPE_LABELS[type] ?? type.replace(/_/g, " ");
}

export const MEASUREMENT_PHASE_LABELS: Record<number, string> = {
  1: "Observed change",
  2: "Change compared with a similar previous period",
  3: "Estimated personal effect",
};

export const PREDICTION_STATUS_LABELS: Record<string, string> = {
  success: "Estimated",
  insufficient_history: "Building history",
  no_prediction: "No estimate",
  failed: "Not computed",
};

export function predictionStatusLabel(status: string | null | undefined): string {
  if (!status) return "—";
  return PREDICTION_STATUS_LABELS[status.toLowerCase()] ?? status.replace(/_/g, " ").toLowerCase();
}
