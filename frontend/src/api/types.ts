/**
 * TypeScript mirrors of the Phase 15 API's Pydantic response models
 * (app/api/schemas/*.py). Kept in one file, hand-synchronized with the
 * backend contracts -- the UI never invents a field the API doesn't
 * actually return, and never computes a value the backend already
 * computes (see docs/ui_architecture.md "API consumption").
 */

export type ConfidenceLabel = "high" | "moderate" | "low" | "no_prediction";
export type SafetySeverity = "MODERATE" | "HIGH";
export type PersonalizationPhase = "literature" | "personal_ranking" | "personal_effect" | "adaptive_policy";

export interface ErrorResponse {
  error: string;
  message: string;
  detail: string | null;
  correlation_id: string | null;
}

export interface HealthResponse {
  application_available: boolean;
  database_connected: boolean;
  model_artifacts_available: boolean;
  configuration_loaded: boolean;
  api_version: string;
  environment: string;
}

export interface ParticipantResponse {
  participant_id: number;
  participant_code: string;
  chronotype: string | null;
  estimated_biological_clock: string | null;
  adapted_biological_clock: string | null;
  current_alignment_score: number | null;
  status: string;
  enrollment_date: string;
  boundary_note: string;
}

export interface OnboardingRequest {
  participant_code: string;
  enrollment_date?: string | null;
  chronotype?: string | null;
  meq_score?: number | null;
  msfsc_time?: string | null;
}

export interface OnboardingResponse {
  participant_id: number;
  participant_code: string;
  status: string;
  note: string;
}

export interface AlignmentComponents {
  sleep_consistency: number | null;
  morning_light: number | null;
  evening_screen: number | null;
  meal_timing: number | null;
  social_jetlag: number | null;
}

export interface AlignmentSummary {
  score: number | null;
  phase_score: number | null;
  behavioral_score: number | null;
  components: AlignmentComponents | null;
  ideal_sleep_onset: string | null;
  actual_sleep_onset: string | null;
}

export interface ConfidenceSummary {
  score: number | null;
  label: ConfidenceLabel | null;
  approximate: boolean;
}

export interface ContributorSummary {
  rank: number;
  signal: string;
  effect_minutes: number | null;
  alignment_deficit: number | null;
  contributor_score: number | null;
  direction: string | null;
  today_anomaly: boolean | null;
}

export interface RecommendationSummary {
  available: boolean;
  suppressed: boolean;
  intervention_type: string | null;
  text: string | null;
  target_display: string | null;
  expected_improvement_minutes: number | null;
  expected_improvement_source: string | null;
}

export interface PrimaryRecommendation {
  intervention_type: string;
  text: string;
  target_display: string | null;
  expected_improvement_minutes: number | null;
  expected_improvement_source: string | null;
}

export interface RecommendationResponse {
  participant_id: number;
  available: boolean;
  suppressed: boolean;
  primary: PrimaryRecommendation | null;
  supporting: PrimaryRecommendation[];
  personalization_phase: PersonalizationPhase | string | null;
  safety_message: string | null;
  non_diagnostic_statement: string | null;
}

export interface SafetySummary {
  active: boolean;
  highest_severity: SafetySeverity | null;
  recommendation_suppressed: boolean;
  flag_types: string[];
}

export interface StatusResponse {
  participant_id: number;
  prediction_available: boolean;
  biological_clock: string | null;
  chronotype: string | null;
  approximate: boolean;
  alignment: AlignmentSummary;
  confidence: ConfidenceSummary;
  contributors: ContributorSummary[];
  recommendation: RecommendationSummary;
  safety: SafetySummary;
  target_date: string | null;
  boundary_note: string;
  qualifier_message: string | null;
}

export interface InferenceRequest {
  target_date?: string | null;
  force_rerun?: boolean;
}

export interface InferenceResponse {
  participant_id: number;
  target_date: string;
  pipeline_status: "SUCCESS" | "INSUFFICIENT_HISTORY" | "NO_PREDICTION" | "FAILED";
  idempotent_short_circuit: boolean;
  persistence_status: string;
  status: StatusResponse;
}

export interface CircadianHistoryEntry {
  date: string;
  biological_clock: string | null;
  confidence_score: number | null;
  confidence_label: string | null;
  alignment_score: number | null;
  disagreement_regime: string | null;
  prediction_status: string;
}

export interface CircadianHistoryResponse {
  participant_id: number;
  entries: CircadianHistoryEntry[];
  count: number;
}

export interface BehaviorEntry {
  date: string;
  sleep_onset: string | null;
  morning_light_duration_minutes: number | null;
  evening_screen_duration_minutes: number | null;
  last_meal_time: string | null;
  exercise_time: string | null;
  is_free_day: boolean | null;
}

export interface BehaviorHistoryResponse {
  participant_id: number;
  entries: BehaviorEntry[];
  count: number;
}

export interface ContributorsResponse {
  participant_id: number;
  target_date: string | null;
  contributors: ContributorSummary[];
  note: string;
}

export interface InterventionHistoryEntry {
  intervention_log_id: number;
  intervention_code: string;
  intervention_type: string;
  log_date: string;
  target_display: string | null;
  actual_display: string | null;
  compliance_degree: number | null;
  compliance_binary: boolean | null;
  observation_status: "observed" | "missing";
  measurement_phase: number | null;
  effect_estimate: number | null;
}

export interface InterventionHistoryResponse {
  participant_id: number;
  entries: InterventionHistoryEntry[];
  count: number;
}

export interface OutcomeSubmissionRequest {
  observation_date: string;
  actual_value_time?: string | null;
  actual_value_numeric?: number | null;
  observed?: boolean;
}

export interface OutcomeSubmissionResponse {
  intervention_log_id: number;
  observation_date: string;
  compliance_degree: number | null;
  compliance_binary: boolean | null;
  applied: boolean;
}

export interface DailyEntryRequest {
  observation_date: string;
  sleep_onset_time?: string | null;
  sleep_offset_time?: string | null;
  morning_light_start_time?: string | null;
  morning_light_duration_minutes?: number | null;
  evening_screen_end_time?: string | null;
  evening_screen_duration_minutes?: number | null;
  last_meal_time?: string | null;
  exercise_time?: string | null;
  last_caffeine_time?: string | null;
  caffeine_amount_mg?: number | null;
  is_free_day?: boolean | null;
}

export interface DailyEntryResponse {
  participant_id: number;
  observation_date: string;
  saved: boolean;
}

export interface SafetyFlagEntry {
  flag_type: string;
  severity: SafetySeverity;
  message_key: string | null;
  first_detected_date: string | null;
  last_observed_date: string | null;
}

export interface SafetyStatusResponse {
  participant_id: number;
  active_flags: SafetyFlagEntry[];
  highest_severity: SafetySeverity | null;
  prediction_available: boolean;
  recommendation_suppressed: boolean;
  non_diagnostic_message_key: string | null;
  boundary_note: string;
}
