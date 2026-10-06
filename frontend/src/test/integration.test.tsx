import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { buildRecommendation, buildStatus } from "./fixtures";
import type {
  CircadianHistoryResponse,
  InterventionHistoryResponse,
  OnboardingResponse,
  RecommendationResponse,
  StatusResponse,
} from "../api/types";

/**
 * End-to-end UI flows, mounted through the real router (<App/>) with
 * only `fetch` mocked -- these exercise page composition and
 * navigation together, on top of the component-level tests. Covers
 * the 8 required flows: onboarding, dashboard load, inference,
 * status refresh after inference, recommendation display, safety
 * suppression, history loading, and daily-entry submission (the
 * implemented analogue of "intervention feedback" -- see
 * docs/ui_architecture.md "Limitations" for why there is no separate
 * manual outcome-confirmation UI: compliance is derived automatically
 * from logged behavior by Phase 12, not self-reported).
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

function installFetchMock(handlers: { status?: StatusResponse; recommendation?: RecommendationResponse | null }) {
  const calls: string[] = [];
  let currentStatus = handlers.status ?? buildStatus();
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = init?.method ?? "GET";
    calls.push(`${method} ${url}`);

    if (url.includes("/onboarding") === false && url.endsWith("/participants") && method === "POST") {
      const body: OnboardingResponse = {
        participant_id: 42,
        participant_code: "P000042",
        status: "active",
        note: "Baseline recorded. A prediction becomes available once daily inference has data to work with.",
      };
      return jsonResponse(body, 201);
    }
    if (url.includes("/status")) {
      return jsonResponse(currentStatus);
    }
    if (url.includes("/inference") && method === "POST") {
      currentStatus = buildStatus({ biological_clock: "23:55", target_date: "2026-06-09" });
      return jsonResponse({
        participant_id: 1,
        target_date: "2026-06-09",
        pipeline_status: "SUCCESS",
        idempotent_short_circuit: false,
        persistence_status: "written",
        status: currentStatus,
      });
    }
    if (url.includes("/recommendation/current")) {
      if (handlers.recommendation === null) {
        return jsonResponse({ error: "not_found", message: "no recommendation", detail: null, correlation_id: null }, 404);
      }
      return jsonResponse(handlers.recommendation ?? buildRecommendation());
    }
    if (url.includes("/circadian/history")) {
      return jsonResponse(emptyHistory);
    }
    if (url.includes("/interventions")) {
      return jsonResponse(emptyInterventions);
    }
    if (url.includes("/behavior") && method === "POST") {
      return jsonResponse({ participant_id: 1, observation_date: "2026-06-09", saved: true }, 201);
    }
    return jsonResponse({ error: "not_found", message: "unhandled in test", detail: null, correlation_id: null }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, calls };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("End-to-end UI flows", () => {
  // --- 1. Onboarding flow ---
  it("completes onboarding and lands on the new participant's daily-entry page", async () => {
    installFetchMock({});
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/onboarding"]}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByText("Welcome to CircadianIQ")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Get started" }));
    await user.click(screen.getByLabelText("I understand"));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.type(screen.getByLabelText("Choose a participant code"), "P000042");
    await user.click(screen.getByRole("button", { name: "Finish" }));

    expect(await screen.findByText("You're all set, P000042")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText("Log today's behavior")).toBeInTheDocument();
  });

  // --- 2. Dashboard load + 5. recommendation display ---
  it("loads the dashboard for an existing participant and shows the primary recommendation", async () => {
    installFetchMock({});
    render(
      <MemoryRouter initialEntries={["/dashboard/1"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Estimated Biological Clock")).toBeInTheDocument();
    expect(screen.getByText("This week's primary focus")).toBeInTheDocument();
    expect(screen.getByText("Try stopping screens by 12:00 AM.")).toBeInTheDocument();
  });

  // --- 3. Inference flow + 4. status refresh ---
  it("runs inference on demand and refreshes the displayed status", async () => {
    installFetchMock({});
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/dashboard/1"]}>
        <App />
      </MemoryRouter>,
    );

    await screen.findByText("Estimated Biological Clock");
    await user.click(screen.getByRole("button", { name: "Update today's estimate" }));

    await waitFor(() => {
      expect(screen.getByRole("img", { name: /11:55 PM/ })).toBeInTheDocument();
    });
  });

  // --- 6. Safety suppression ---
  it("suppresses the recommendation card and shows the safety banner under a high-severity flag", async () => {
    installFetchMock({
      status: buildStatus({
        safety: { active: true, highest_severity: "HIGH", recommendation_suppressed: true, flag_types: ["restriction_pattern"] },
      }),
      recommendation: buildRecommendation({
        suppressed: true,
        available: false,
        primary: null,
        safety_message: "We've paused personalized recommendations while this pattern continues.",
      }),
    });
    render(
      <MemoryRouter initialEntries={["/dashboard/1"]}>
        <App />
      </MemoryRouter>,
    );

    await screen.findByText("Estimated Biological Clock");
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(/paused personalized recommendations/i)).toBeInTheDocument();
    expect(screen.queryByText("This week's primary focus")).not.toBeInTheDocument();
  });

  // --- 7. History loading ---
  it("loads circadian history for the trajectory chart", async () => {
    const { calls } = installFetchMock({});
    render(
      <MemoryRouter initialEntries={["/dashboard/1"]}>
        <App />
      </MemoryRouter>,
    );

    await screen.findByText("Estimated Biological Clock");
    await waitFor(() => {
      expect(calls.some((c) => c.includes("/circadian/history"))).toBe(true);
    });
  });

  // --- 8. Daily-entry submission (implemented feedback/logging flow) ---
  it("submits a daily behavioral entry", async () => {
    installFetchMock({});
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/log/1"]}>
        <App />
      </MemoryRouter>,
    );

    await user.type(screen.getByLabelText("Sleep onset"), "23:30");
    await user.click(screen.getByRole("button", { name: "Save today's entry" }));

    expect(await screen.findByText(/Saved 2026-06-09/)).toBeInTheDocument();
  });
});

describe("Navigation", () => {
  it("navigates from the participant picker to onboarding via a real router link", async () => {
    installFetchMock({});
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    await user.click(screen.getByRole("link", { name: "Create a participant profile" }));
    expect(screen.getByText("Welcome to CircadianIQ")).toBeInTheDocument();
  });
});
