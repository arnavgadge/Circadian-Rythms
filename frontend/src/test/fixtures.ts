import type { RecommendationResponse, StatusResponse } from "../api/types";

export function buildStatus(overrides: Partial<StatusResponse> = {}): StatusResponse {
  return {
    participant_id: 1,
    prediction_available: true,
    biological_clock: "23:48",
    chronotype: "Late",
    approximate: false,
    alignment: {
      score: 68,
      phase_score: 72,
      behavioral_score: 62,
      components: {
        sleep_consistency: 70,
        morning_light: 55,
        evening_screen: 40,
        meal_timing: 80,
        social_jetlag: 65,
      },
      ideal_sleep_onset: "01:48",
      actual_sleep_onset: "02:10",
    },
    confidence: { score: 84, label: "high", approximate: false },
    contributors: [
      { rank: 1, signal: "evening_screen", effect_minutes: 28, alignment_deficit: 60, contributor_score: 78, direction: "hurting", today_anomaly: true },
      { rank: 2, signal: "morning_light", effect_minutes: -17, alignment_deficit: 45, contributor_score: 42, direction: "opportunity_missed", today_anomaly: false },
      { rank: 3, signal: "social_jetlag", effect_minutes: null, alignment_deficit: 42, contributor_score: 42, direction: "hurting", today_anomaly: null },
    ],
    recommendation: {
      available: true,
      suppressed: false,
      intervention_type: "screen",
      text: "Try stopping screens by 12:00 AM.",
      target_display: "12:00 AM",
      expected_improvement_minutes: 15,
      expected_improvement_source: "literature",
    },
    safety: { active: false, highest_severity: null, recommendation_suppressed: false, flag_types: [] },
    target_date: "2026-06-08",
    boundary_note: "Estimated from behavioral patterns. Not a clinical measurement.",
    qualifier_message: null,
    ...overrides,
  };
}

export function buildRecommendation(overrides: Partial<RecommendationResponse> = {}): RecommendationResponse {
  return {
    participant_id: 1,
    available: true,
    suppressed: false,
    primary: {
      intervention_type: "screen",
      text: "Try stopping screens by 12:00 AM.",
      target_display: "12:00 AM",
      expected_improvement_minutes: 15,
      expected_improvement_source: "literature",
    },
    supporting: [],
    personalization_phase: "literature",
    safety_message: null,
    non_diagnostic_statement: null,
    ...overrides,
  };
}
