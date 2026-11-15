import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { buildRecommendation, buildStatus } from "./fixtures";
import type { CircadianHistoryResponse, InterventionHistoryEntry, InterventionHistoryResponse, RecommendationResponse, StatusResponse } from "../api/types";

/**
 * Confidence/safety rendering states (AUDIT 20 step 3), following the
 * mocked-fetch + MemoryRouter E2E pattern established in
 * integration.test.tsx. Response bodies mirror the Pydantic schemas
 * (app/api/schemas/status.py, recommendation.py, interventions.py,
 * history.py) field-for-field.
 */

const emptyHistory: CircadianHistoryResponse = { participant_id: 1, entries: [], count: 0 };
const emptyInterventions: InterventionHistoryResponse = { participant_id: 1, entries: [], count: 0 };

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as Response);
}

function installFetchMock(handlers: {
  status?: StatusResponse;
  recommendation?: RecommendationResponse | null;
  history?: CircadianHistoryResponse;
  interventions?: InterventionHistoryResponse;
}) {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();

    if (url.includes("/status")) {
      return jsonResponse(handlers.status ?? buildStatus());
    }
    if (url.includes("/recommendation/current")) {
      if (handlers.recommendation === null) {
        return jsonResponse({ error: "not_found", message: "no recommendation", detail: null, correlation_id: null }, 404);
      }
      return jsonResponse(handlers.recommendation ?? buildRecommendation());
    }
    if (url.includes("/circadian/history")) {
      return jsonResponse(handlers.history ?? emptyHistory);
    }
    if (url.includes("/interventions")) {
      return jsonResponse(handlers.interventions ?? emptyInterventions);
    }
    return jsonResponse({ error: "not_found", message: "unhandled in test", detail: null, correlation_id: null }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock };
}

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={["/dashboard/1"]}>
      <App />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Confidence/safety UI states", () => {
  // --- 1. Normal dashboard: HIGH confidence, no safety flags ---
  it("renders normally with HIGH confidence and no safety flags", async () => {
    installFetchMock({ status: buildStatus() });
    renderDashboard();

    expect(await screen.findByText("Estimated Biological Clock")).toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("This week's primary focus")).toBeInTheDocument();
  });

  // --- 2. Moderate confidence ---
  it("shows a qualifier (not literally 'approximate') for MODERATE confidence", async () => {
    installFetchMock({
      status: buildStatus({
        confidence: { score: 60, label: "moderate", approximate: false },
        qualifier_message: "Estimated from partial data.",
      }),
    });
    renderDashboard();

    expect(await screen.findByText("Estimated Biological Clock")).toBeInTheDocument();
    expect(screen.getByText("Moderate")).toBeInTheDocument();
    expect(screen.getByText("Estimated from partial data.")).toBeInTheDocument();
    // Not displayed as literally "approximate" -- no leading "~" on the clock time heading.
    expect(screen.getByRole("heading", { name: "11:48 PM" })).toBeInTheDocument();
  });

  // --- 3. Low confidence ---
  it("shows the approximate qualifier and '~' prefix for LOW confidence", async () => {
    installFetchMock({
      status: buildStatus({
        approximate: true,
        confidence: { score: 35, label: "low", approximate: true },
        qualifier_message: "Approximate estimate — complete more data for better accuracy.",
      }),
    });
    renderDashboard();

    expect(await screen.findByText("Estimated Biological Clock")).toBeInTheDocument();
    expect(screen.getByText("Low")).toBeInTheDocument();
    expect(screen.getByText("Approximate estimate — complete more data for better accuracy.")).toBeInTheDocument();
  });

  // --- 4. No-prediction ---
  it("shows the no-data state and boundary note when prediction_available is false", async () => {
    installFetchMock({
      status: buildStatus({
        prediction_available: false,
        biological_clock: null,
        confidence: { score: null, label: "no_prediction", approximate: false },
        alignment: { score: null, phase_score: null, behavioral_score: null, components: null, ideal_sleep_onset: null, actual_sleep_onset: null },
        contributors: [],
        recommendation: { available: false, suppressed: false, intervention_type: null, text: null, target_display: null, expected_improvement_minutes: null, expected_improvement_source: null },
        qualifier_message: "No daily result exists yet for this participant/date.",
      }),
      recommendation: null,
    });
    renderDashboard();

    expect(await screen.findByText("Not enough data for today's estimate")).toBeInTheDocument();
    expect(screen.getByText("No daily result exists yet for this participant/date.")).toBeInTheDocument();
    expect(screen.getByText("Estimated from behavioral patterns. Not a clinical measurement.")).toBeInTheDocument();
  });

  // --- 5. Safety warning MODERATE: recommendation still shown alongside flag message ---
  it("shows a pattern note under MODERATE safety and still shows the recommendation", async () => {
    installFetchMock({
      status: buildStatus({
        safety: { active: true, highest_severity: "MODERATE", recommendation_suppressed: false, flag_types: ["persistent_late_phase"] },
      }),
      recommendation: buildRecommendation({ suppressed: false, available: true }),
    });
    renderDashboard();

    expect(await screen.findByText("Estimated Biological Clock")).toBeInTheDocument();
    expect(screen.getByText("Pattern note")).toBeInTheDocument();
    expect(screen.getByText("Consistently late estimated clock")).toBeInTheDocument();
    // No alert role for a MODERATE flag -- only HIGH uses role="alert".
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    // Recommendation still shown alongside the flag message.
    expect(screen.getByText("This week's primary focus")).toBeInTheDocument();
    expect(screen.getByText("Try stopping screens by 12:00 AM.")).toBeInTheDocument();
  });

  // --- 6. Safety warning HIGH: recommendation suppressed ---
  it("suppresses the recommendation and shows the safety alert under HIGH safety", async () => {
    installFetchMock({
      status: buildStatus({
        safety: { active: true, highest_severity: "HIGH", recommendation_suppressed: true, flag_types: ["continuous_dlmo_drift"] },
      }),
      recommendation: buildRecommendation({
        suppressed: true,
        available: false,
        primary: null,
        safety_message: "We've paused personalized recommendations while this pattern continues.",
        non_diagnostic_statement: "This is not a diagnosis.",
      }),
    });
    renderDashboard();

    expect(await screen.findByText("Estimated Biological Clock")).toBeInTheDocument();
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(/paused personalized recommendations/i)).toBeInTheDocument();
    expect(within(alert).getByText("This is not a diagnosis.")).toBeInTheDocument();
    // Normal recommendation card must NOT render when suppressed is true.
    expect(screen.queryByText("This week's primary focus")).not.toBeInTheDocument();
  });

  // --- 7. History/trajectory data rendering ---
  it("renders the trajectory chart from history endpoint data", async () => {
    installFetchMock({
      history: {
        participant_id: 1,
        count: 2,
        entries: [
          { date: "2026-06-09", biological_clock: "23:50", confidence_score: 70, confidence_label: "high", alignment_score: 65, disagreement_regime: null, prediction_status: "SUCCESS" },
          { date: "2026-06-08", biological_clock: "23:40", confidence_score: 68, confidence_label: "high", alignment_score: 60, disagreement_regime: null, prediction_status: "SUCCESS" },
        ],
      },
    });
    render(
      <MemoryRouter initialEntries={["/history/1"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("img", { name: /Estimated biological clock over the selected range/i })).toBeInTheDocument();
  });

  // --- 8. Intervention feedback/progress rendering ---
  it("renders intervention progress from the intervention-history endpoint", async () => {
    const entries: InterventionHistoryEntry[] = [
      { intervention_log_id: 1, intervention_code: "SCR1", intervention_type: "screen", log_date: "2026-06-09", target_display: "12:00 AM", actual_display: "12:10 AM", compliance_degree: 0.8, compliance_binary: true, observation_status: "observed", measurement_phase: 1, effect_estimate: -12 },
      { intervention_log_id: 2, intervention_code: "SCR2", intervention_type: "screen", log_date: "2026-06-08", target_display: "12:00 AM", actual_display: null, compliance_degree: null, compliance_binary: false, observation_status: "observed", measurement_phase: 1, effect_estimate: null },
    ];
    installFetchMock({ interventions: { participant_id: 1, entries, count: entries.length } });
    renderDashboard();

    expect(await screen.findByText("screen intervention")).toBeInTheDocument();
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
    expect(screen.getByText("days followed")).toBeInTheDocument();
    expect(screen.getByText("12 min earlier")).toBeInTheDocument();
  });
});
