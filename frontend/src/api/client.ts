/**
 * Centralized, typed API client for the Phase 15 CircadianIQ API.
 * No component calls fetch() directly -- every request/response type
 * here corresponds to a Phase 15 Pydantic schema (see ./types.ts).
 *
 * The API base URL is read from build-time configuration
 * (VITE_API_BASE_URL), never hard-coded secrets or credentials.
 */

import type {
  BehaviorHistoryResponse,
  CircadianHistoryResponse,
  ContributorsResponse,
  DailyEntryRequest,
  DailyEntryResponse,
  HealthResponse,
  InferenceRequest,
  InferenceResponse,
  InterventionHistoryResponse,
  OnboardingRequest,
  OnboardingResponse,
  OutcomeSubmissionRequest,
  OutcomeSubmissionResponse,
  ParticipantResponse,
  RecommendationResponse,
  SafetyStatusResponse,
  StatusResponse,
} from "./types";

const BASE_URL: string = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000/api/v1";

/** Thrown for any non-2xx API response; carries the parsed structured
 * error body when the API returned one (never a raw stack trace). */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: string | null;
  readonly correlationId: string | null;

  constructor(status: number, code: string, message: string, detail: string | null, correlationId: string | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.correlationId = correlationId;
  }
}

async function request<TResponse>(path: string, init?: RequestInit): Promise<TResponse> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "network_error", "Could not reach the CircadianIQ API.", null, null);
  }

  if (!response.ok) {
    let body: Partial<{ error: string; message: string; detail: string | null; correlation_id: string | null }> = {};
    try {
      body = await response.json();
    } catch {
      // Non-JSON error body -- fall through to the generic message below.
    }
    throw new ApiError(
      response.status,
      body.error ?? "error",
      body.message ?? `Request failed with status ${response.status}.`,
      body.detail ?? null,
      body.correlation_id ?? response.headers.get("X-Correlation-ID"),
    );
  }

  if (response.status === 204) {
    return undefined as TResponse;
  }
  return (await response.json()) as TResponse;
}

export const api = {
  getHealth: () => request<HealthResponse>("/health"),

  onboardParticipant: (body: OnboardingRequest) =>
    request<OnboardingResponse>("/participants", { method: "POST", body: JSON.stringify(body) }),

  getParticipant: (participantId: number) => request<ParticipantResponse>(`/participants/${participantId}`),

  getStatus: (participantId: number, targetDate?: string) =>
    request<StatusResponse>(`/participants/${participantId}/status${targetDate ? `?target_date=${targetDate}` : ""}`),

  runInference: (participantId: number, body: InferenceRequest = {}) =>
    request<InferenceResponse>(`/participants/${participantId}/inference`, { method: "POST", body: JSON.stringify(body) }),

  getCircadianHistory: (participantId: number, params?: { start_date?: string; end_date?: string; limit?: number }) =>
    request<CircadianHistoryResponse>(`/participants/${participantId}/circadian/history${toQuery(params)}`),

  getBehaviorHistory: (participantId: number, params?: { start_date?: string; end_date?: string; limit?: number }) =>
    request<BehaviorHistoryResponse>(`/participants/${participantId}/behavior${toQuery(params)}`),

  recordDailyEntry: (participantId: number, body: DailyEntryRequest) =>
    request<DailyEntryResponse>(`/participants/${participantId}/behavior`, { method: "POST", body: JSON.stringify(body) }),

  getCurrentContributors: (participantId: number) =>
    request<ContributorsResponse>(`/participants/${participantId}/contributors/current`),

  getCurrentRecommendation: (participantId: number) =>
    request<RecommendationResponse>(`/participants/${participantId}/recommendation/current`),

  getInterventionHistory: (
    participantId: number,
    params?: { start_date?: string; end_date?: string; intervention_type?: string; limit?: number },
  ) => request<InterventionHistoryResponse>(`/participants/${participantId}/interventions${toQuery(params)}`),

  submitInterventionOutcome: (participantId: number, interventionLogId: number, body: OutcomeSubmissionRequest) =>
    request<OutcomeSubmissionResponse>(`/participants/${participantId}/interventions/${interventionLogId}/outcome`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getSafetyStatus: (participantId: number) => request<SafetyStatusResponse>(`/participants/${participantId}/safety`),
};

function toQuery(params?: Record<string, string | number | undefined>): string {
  if (!params) return "";
  const entries = Object.entries(params).filter(([, v]) => v !== undefined) as [string, string | number][];
  if (entries.length === 0) return "";
  const search = new URLSearchParams(entries.map(([k, v]) => [k, String(v)]));
  return `?${search.toString()}`;
}
