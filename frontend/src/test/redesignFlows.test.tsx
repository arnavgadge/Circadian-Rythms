import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { buildRecommendation, buildStatus } from "./fixtures";
import type { BehaviorEntry, InterventionHistoryEntry, StatusResponse } from "../api/types";

/**
 * Flows added or reworked by the "Personal Time Atlas" redesign:
 * participant lookup, request payloads (regression for the stale
 * useAction closure), date navigation, timeline/heatmap rendering from
 * real responses, range re-requests, the intervention outcome form and
 * Research Mode. Only `fetch` is mocked; every request is recorded.
 */

interface Call {
  method: string;
  url: string;
  body: unknown;
}

type Handler = (url: string, method: string) => { status: number; body: unknown } | undefined;

function installFetch(handler: Handler) {
  const calls: Call[] = [];
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = init?.method ?? "GET";
    calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const res = handler(url, method) ?? { status: 404, body: { error: "not_found", message: "unhandled", detail: null, correlation_id: null } };
    return Promise.resolve({ ok: res.status < 300, status: res.status, json: () => Promise.resolve(res.body), headers: new Headers() } as Response);
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

function dashboardHandler(overrides: { status?: StatusResponse; behavior?: BehaviorEntry[] } = {}): Handler {
  return (url, method) => {
    if (url.includes("/status")) return { status: 200, body: overrides.status ?? buildStatus() };
    if (url.includes("/recommendation/current")) return { status: 200, body: buildRecommendation() };
    if (url.includes("/interventions")) return { status: 200, body: { participant_id: 1, entries: [], count: 0 } };
    if (url.includes("/circadian/history")) return { status: 200, body: { participant_id: 1, entries: [], count: 0 } };
    if (url.includes("/behavior") && method === "GET") {
      const entries = overrides.behavior ?? [];
      return { status: 200, body: { participant_id: 1, entries, count: entries.length } };
    }
    if (url.includes("/inference")) return { status: 200, body: {} };
    return undefined;
  };
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Participant entry", () => {
  it("looks the participant up through the existing endpoint before opening the dashboard", async () => {
    const calls = installFetch((url, method) => {
      if (url.endsWith("/participants/1") && method === "GET") {
        return {
          status: 200,
          body: { participant_id: 1, participant_code: "P1", chronotype: null, estimated_biological_clock: null, adapted_biological_clock: null, current_alignment_score: null, status: "active", enrollment_date: "2026-06-01", boundary_note: "x" },
        };
      }
      return dashboardHandler()(url, method);
    });
    const user = userEvent.setup();
    renderAt("/");

    await user.type(screen.getByLabelText("Participant ID"), "1");
    await user.click(screen.getByRole("button", { name: "View dashboard" }));

    expect(await screen.findByRole("heading", { name: "Your biological time map" })).toBeInTheDocument();
    expect(calls[0]).toMatchObject({ method: "GET" });
    expect(calls[0].url).toMatch(/\/participants\/1$/);
  });

  it("shows an inline message for an unknown participant and stays on the entry screen", async () => {
    installFetch(() => undefined);
    const user = userEvent.setup();
    renderAt("/");

    await user.type(screen.getByLabelText("Participant ID"), "99");
    await user.click(screen.getByRole("button", { name: "View dashboard" }));

    expect(await screen.findByText(/No participant with ID 99 was found/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Your biological time map" })).not.toBeInTheDocument();
  });
});

describe("Request payloads (regression: actions use the latest form values)", () => {
  it("sends the values typed into the daily-entry form", async () => {
    const calls = installFetch((url, method) => {
      if (url.includes("/behavior") && method === "POST") return { status: 201, body: { participant_id: 1, observation_date: "2026-06-05", saved: true } };
      if (url.includes("/behavior")) return { status: 200, body: { participant_id: 1, entries: [], count: 0 } };
      return undefined;
    });
    const user = userEvent.setup();
    renderAt("/log/1?date=2026-06-05");

    await user.type(screen.getByLabelText("Sleep onset"), "23:30");
    await user.type(screen.getAllByLabelText("Duration (minutes)")[0], "45");
    await user.type(screen.getByLabelText("Amount (mg)"), "80");
    await user.click(screen.getByRole("button", { name: "Save today's entry" }));

    await screen.findByText(/Saved 2026-06-05/);
    const post = calls.find((c) => c.method === "POST");
    expect(post?.body).toEqual({
      observation_date: "2026-06-05",
      sleep_onset_time: "23:30",
      sleep_offset_time: null,
      morning_light_start_time: null,
      morning_light_duration_minutes: 45,
      evening_screen_end_time: null,
      evening_screen_duration_minutes: null,
      last_meal_time: null,
      exercise_time: null,
      last_caffeine_time: null,
      caffeine_amount_mg: 80,
    });
  });

  it("sends the participant code typed during onboarding", async () => {
    const calls = installFetch((url, method) => {
      if (url.endsWith("/participants") && method === "POST") return { status: 201, body: { participant_id: 7, participant_code: "P000777", status: "active", note: "ok" } };
      return undefined;
    });
    const user = userEvent.setup();
    renderAt("/onboarding");

    await user.click(screen.getByRole("button", { name: "Get started" }));
    await user.click(screen.getByLabelText("I understand"));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.type(screen.getByLabelText("Choose a participant code"), "P000777");
    await user.click(screen.getByRole("button", { name: "Finish" }));

    await screen.findByText("You're all set, P000777");
    expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({ participant_code: "P000777", meq_score: 50, msfsc_time: null });
  });

  it("pre-fills values already saved for the selected date", async () => {
    installFetch((url) => {
      if (url.includes("/behavior")) {
        const entry: BehaviorEntry = { date: "2026-06-05", sleep_onset: "23:10", morning_light_duration_minutes: 30, evening_screen_duration_minutes: null, last_meal_time: "20:15", exercise_time: null, is_free_day: null };
        return { status: 200, body: { participant_id: 1, entries: [entry], count: 1 } };
      }
      return undefined;
    });
    renderAt("/log/1?date=2026-06-05");

    await waitFor(() => expect(screen.getByLabelText("Sleep onset")).toHaveValue("23:10"));
    expect(screen.getByLabelText("Last meal")).toHaveValue("20:15");
    expect(screen.getAllByLabelText("Duration (minutes)")[0]).toHaveValue(30);
    expect(screen.getByText(/An entry already exists/)).toBeInTheDocument();
  });

  it("shows stored durations rounded and never overwrites them when left unchanged", async () => {
    const calls = installFetch((url, method) => {
      if (url.includes("/behavior") && method === "POST") return { status: 201, body: { participant_id: 1, observation_date: "2026-06-05", saved: true } };
      if (url.includes("/behavior")) {
        const entry: BehaviorEntry = { date: "2026-06-05", sleep_onset: "23:10", morning_light_duration_minutes: 34.5365, evening_screen_duration_minutes: 71.075, last_meal_time: null, exercise_time: null, is_free_day: null };
        return { status: 200, body: { participant_id: 1, entries: [entry], count: 1 } };
      }
      return undefined;
    });
    const user = userEvent.setup();
    renderAt("/log/1?date=2026-06-05");

    const [light, screenDuration] = screen.getAllByLabelText("Duration (minutes)");
    await waitFor(() => expect(light).toHaveValue(35));
    expect(screenDuration).toHaveValue(71);

    await user.clear(screenDuration);
    await user.type(screenDuration, "90");
    await user.click(screen.getByRole("button", { name: "Save today's entry" }));

    await screen.findByText(/Saved 2026-06-05/);
    const body = calls.find((c) => c.method === "POST")?.body as Record<string, unknown>;
    expect(body.morning_light_duration_minutes).toBeNull(); // untouched -> stored 34.5365 kept by the upsert
    expect(body.evening_screen_duration_minutes).toBe(90); // edited -> sent
    expect(body.sleep_onset_time).toBe("23:10");
  });
});

describe("Dashboard", () => {
  it("never runs inference just by rendering, and re-requests status for a chosen date", async () => {
    const calls = installFetch(dashboardHandler());
    const user = userEvent.setup();
    renderAt("/dashboard/1");

    await screen.findByText("Estimated Biological Clock");
    await user.click(screen.getByRole("button", { name: "Previous day" }));

    await waitFor(() => expect(calls.some((c) => c.url.includes("/status?target_date=2026-06-07"))).toBe(true));
    expect(calls.some((c) => c.url.includes("/inference"))).toBe(false);
  });

  it("lays out the shown day's logged behavior, without inventing times the API doesn't return", async () => {
    installFetch(
      dashboardHandler({
        behavior: [{ date: "2026-06-08", sleep_onset: "23:30", morning_light_duration_minutes: 42, evening_screen_duration_minutes: 198, last_meal_time: "20:00", exercise_time: null, is_free_day: null }],
      }),
    );
    renderAt("/dashboard/1");

    const timeline = await screen.findByRole("group", { name: /Logged behavior across the day/ });
    expect(within(timeline).getByText("Onset 11:30 PM")).toBeInTheDocument();
    expect(within(timeline).getByText("Last meal 8:00 PM")).toBeInTheDocument();
    expect(within(timeline).getByText("Evening screens 3h 18m")).toBeInTheDocument();
    expect(within(timeline).getAllByText("time of day not available")).toHaveLength(2);
    expect(within(timeline).getByText("Not logged")).toBeInTheDocument(); // exercise
  });

  it("shows the research panel when Research Mode is switched on", async () => {
    installFetch(dashboardHandler());
    const user = userEvent.setup();
    renderAt("/dashboard/1");

    await screen.findByText("Estimated Biological Clock");
    expect(screen.queryByText("Research / debug")).not.toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /research mode/i }));
    expect(await screen.findByText("Research / debug")).toBeInTheDocument();
    expect(screen.getByText("confidence_score")).toBeInTheDocument();
  });
});

describe("History", () => {
  it("re-requests both history endpoints when the range changes", async () => {
    const behavior: BehaviorEntry[] = [
      { date: "2026-06-03", sleep_onset: "23:00", morning_light_duration_minutes: 20, evening_screen_duration_minutes: 90, last_meal_time: null, exercise_time: null, is_free_day: null },
      { date: "2026-06-01", sleep_onset: "23:40", morning_light_duration_minutes: null, evening_screen_duration_minutes: 120, last_meal_time: "21:00", exercise_time: null, is_free_day: null },
    ];
    const calls = installFetch((url) => {
      if (url.includes("/circadian/history")) {
        return {
          status: 200,
          body: { participant_id: 1, count: 1, entries: [{ date: "2026-06-03", biological_clock: "22:30", confidence_score: 80, confidence_label: "high", alignment_score: 70, disagreement_regime: null, prediction_status: "success" }] },
        };
      }
      if (url.includes("/behavior")) return { status: 200, body: { participant_id: 1, entries: behavior, count: behavior.length } };
      return undefined;
    });
    const user = userEvent.setup();
    renderAt("/history/1");

    expect(await screen.findByRole("img", { name: /2 of 3 days have logged observations/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "7 days" }));

    await waitFor(() => {
      expect(calls.some((c) => c.url.includes("/circadian/history?limit=7"))).toBe(true);
      expect(calls.some((c) => c.url.includes("/behavior?limit=7"))).toBe(true);
    });
    expect(screen.getByRole("button", { name: "7 days" })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows an editorial empty state, not a fabricated chart, when there is no history", async () => {
    installFetch((url) => {
      if (url.includes("/circadian/history") || url.includes("/behavior")) return { status: 200, body: { participant_id: 1, entries: [], count: 0 } };
      return undefined;
    });
    renderAt("/history/1");

    expect(await screen.findByText("Your history is still being written")).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /over the selected range/ })).not.toBeInTheDocument();
  });
});

describe("Interventions", () => {
  const entries: InterventionHistoryEntry[] = [
    { intervention_log_id: 11, intervention_code: "SCREEN_CUTOFF", intervention_type: "screen", log_date: "2026-06-09", target_display: "00:00", actual_display: null, compliance_degree: null, compliance_binary: null, observation_status: "missing", measurement_phase: null, effect_estimate: null },
    { intervention_log_id: 10, intervention_code: "SCREEN_CUTOFF", intervention_type: "screen", log_date: "2026-06-08", target_display: "00:00", actual_display: "23:50", compliance_degree: 1, compliance_binary: true, observation_status: "observed", measurement_phase: 1, effect_estimate: -12 },
  ];

  it("submits an outcome through the existing endpoint with its exact payload, then refreshes", async () => {
    const calls = installFetch((url, method) => {
      if (url.includes("/outcome") && method === "POST") {
        return { status: 200, body: { intervention_log_id: 11, observation_date: "2026-06-09", compliance_degree: 1, compliance_binary: true, applied: true } };
      }
      if (url.includes("/interventions")) return { status: 200, body: { participant_id: 1, entries, count: entries.length } };
      return undefined;
    });
    const user = userEvent.setup();
    renderAt("/interventions/1");

    expect(await screen.findByRole("heading", { name: "Screen cutoff" })).toBeInTheDocument();
    expect(screen.getByText("12 min earlier", { selector: "p" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Record outcome" }));
    await user.type(screen.getByLabelText("Actual time"), "23:45");
    await user.click(screen.getByRole("button", { name: "Save outcome" }));

    expect(await screen.findByText(/recorded as followed/)).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST");
    expect(post?.url).toMatch(/\/participants\/1\/interventions\/11\/outcome$/);
    expect(post?.body).toEqual({ observation_date: "2026-06-09", actual_value_time: "23:45", actual_value_numeric: null, observed: true });
    await waitFor(() => expect(calls.filter((c) => c.method === "GET" && c.url.includes("/interventions?")).length).toBeGreaterThanOrEqual(2));
  });
});
