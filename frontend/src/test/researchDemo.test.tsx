import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { buildStatus } from "./fixtures";
import { clearDailyStatusCache } from "../hooks/useDailyStatuses";
import { clearParticipantCache } from "../hooks/useParticipant";
import type { BehaviorEntry, CircadianHistoryEntry, InterventionHistoryEntry, ParticipantResponse } from "../api/types";

/**
 * The 30-Day Research Demo reads only existing endpoints. These tests
 * mock `fetch` with a DEMO-001-shaped dataset (30 observation days,
 * 24 persisted results from day 7) and check identity verification,
 * the warm-up boundary, per-day results, caching, and that no
 * inference request is ever made.
 */

const START = "2026-10-05";
const dates = Array.from({ length: 30 }, (_, i) => {
  const d = new Date(Date.UTC(2026, 9, 5 + i));
  return d.toISOString().slice(0, 10);
});
const clockFor = (i: number) => `22:${String(10 + i).padStart(2, "0")}`; // distinct per day

function participant(code = "DEMO-001"): ParticipantResponse {
  return {
    participant_id: 9101,
    participant_code: code,
    chronotype: "Intermediate",
    estimated_biological_clock: null,
    adapted_biological_clock: null,
    current_alignment_score: null,
    status: "active",
    enrollment_date: START,
    boundary_note: "x",
  };
}

const behavior: BehaviorEntry[] = dates.map((d, i) => ({
  date: d,
  sleep_onset: i % 2 ? "23:40" : "00:20",
  morning_light_duration_minutes: 10 + i,
  evening_screen_duration_minutes: 200 - i * 3,
  last_meal_time: "21:00",
  exercise_time: "19:00",
  is_free_day: false,
})).reverse();

const history: CircadianHistoryEntry[] = dates.slice(6).map((d, j) => ({
  date: d,
  biological_clock: clockFor(j + 6),
  confidence_score: 82,
  confidence_label: "high",
  alignment_score: 40 + j,
  disagreement_regime: j === 0 ? "extreme" : "normal",
  prediction_status: "success",
})).reverse();

const interventions: InterventionHistoryEntry[] = dates.slice(6).map((d, j) => ({
  intervention_log_id: 100 + j,
  intervention_code: "EVENING_SCREEN_REDUCTION",
  intervention_type: "screen",
  log_date: d,
  target_display: "21:30",
  actual_display: "22:00",
  compliance_degree: j % 2 ? 1 : 0.25,
  compliance_binary: j % 2 === 1,
  observation_status: "observed" as const,
  measurement_phase: 1,
  effect_estimate: null,
})).reverse();

function install(participantResponse: { status: number; body: unknown } = { status: 200, body: participant() }) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = init?.method ?? "GET";
      calls.push(`${method} ${url}`);
      const reply = (status: number, body: unknown) =>
        Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(body), headers: new Headers() } as Response);
      if (/\/participants\/9101$/.test(url)) return reply(participantResponse.status, participantResponse.body);
      if (url.includes("/status?target_date=")) {
        const d = new URL(url).searchParams.get("target_date")!;
        const i = dates.indexOf(d);
        return reply(
          200,
          buildStatus({
            participant_id: 9101,
            target_date: d,
            biological_clock: clockFor(i),
            recommendation: { ...buildStatus().recommendation, text: `Try stopping screens by day-${i + 1} target.` },
          }),
        );
      }
      if (url.includes("/behavior")) return reply(200, { participant_id: 9101, entries: behavior, count: behavior.length });
      if (url.includes("/circadian/history")) return reply(200, { participant_id: 9101, entries: history, count: history.length });
      if (url.includes("/interventions")) return reply(200, { participant_id: 9101, entries: interventions, count: interventions.length });
      return reply(404, { error: "not_found", message: "unhandled", detail: null, correlation_id: null });
    }),
  );
  return calls;
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
  clearDailyStatusCache();
  clearParticipantCache();
});

describe("30-Day Research Demo", () => {
  it("verifies DEMO-001's identity, labels it synthetic, and opens on the day-1 warm-up", async () => {
    install();
    renderAt("/demo");

    expect(await screen.findByRole("heading", { name: "30-day circadian journey" })).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/Synthetic research participant/i);
    expect(screen.getByText("Day 1 / 30", { selector: ".journey-nav__counter" })).toBeInTheDocument();
    expect(screen.getByText(/Historical warm-up — six complete days required before the first prediction\./)).toBeInTheDocument();
    // Overview counts come from the API responses.
    await waitFor(() => expect(screen.getByText("Recorded behavioral days").nextElementSibling).toHaveTextContent("30"));
    expect(screen.getByText("Valid prediction days").nextElementSibling).toHaveTextContent("24");
  });

  it("shows each day's persisted result, fetches each day once, and never runs inference", async () => {
    const calls = install();
    const user = userEvent.setup();
    renderAt("/demo/9101?day=6");

    await screen.findByText(/Historical warm-up/);
    await user.click(screen.getByRole("button", { name: "Next day" }));
    expect(screen.getByText("Day 7 / 30", { selector: ".journey-nav__counter" })).toBeInTheDocument();

    // Day 7 = first prediction, from the stored status for 2026-10-11.
    const clock = await screen.findByRole("img", { name: /Estimated DLMO \(fused\): 10:16 PM/ });
    expect(clock).toBeInTheDocument();
    expect(screen.getAllByText("Try stopping screens by day-7 target.").length).toBeGreaterThan(0);

    await user.selectOptions(screen.getByLabelText("Day"), "20");
    expect(await screen.findByRole("img", { name: /Estimated DLMO \(fused\): 10:29 PM/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Previous day" }));
    await user.click(screen.getByRole("button", { name: /Day 7, / }));

    await waitFor(() => expect(calls.filter((c) => c.includes("/status?target_date=")).length).toBe(24));
    const statusCalls = calls.filter((c) => c.includes("/status?target_date="));
    expect(new Set(statusCalls).size).toBe(24); // no repeats despite navigating back and forth
    expect(statusCalls.some((c) => c.includes("2026-10-05"))).toBe(false); // warm-up days are never queried
    expect(calls.some((c) => c.startsWith("POST") || c.includes("/inference"))).toBe(false);
  });

  it("marks warm-up and prediction days on the 30-day strip", async () => {
    install();
    renderAt("/demo/9101");
    await screen.findByText("Day 1 / 30", { selector: ".journey-nav__counter" });
    await waitFor(() => expect(screen.getByRole("button", { name: /^Day 7, .*: prediction$/ })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /^Day 6, .*: warm-up$/ })).toBeInTheDocument();
    const strip = screen.getAllByRole("listitem").filter((li) => within(li).queryByRole("button", { name: /^Day \d+, / }));
    expect(strip).toHaveLength(30);
  });

  it("advances day by day with Play", async () => {
    install();
    const user = userEvent.setup();
    renderAt("/demo/9101?day=3");
    await screen.findByText("Day 3 / 30", { selector: ".journey-nav__counter" });
    await user.click(screen.getByRole("button", { name: "Play" }));
    expect(await screen.findByText("Day 4 / 30", { selector: ".journey-nav__counter" }, { timeout: 8000 })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Pause" }));
  }, 15000);

  it("refuses to present another participant as the demonstration", async () => {
    install({ status: 200, body: participant("P000777") });
    renderAt("/demo");
    expect(await screen.findByText(/not DEMO-001/)).toBeInTheDocument();
    expect(screen.queryByText("Day 1 / 30", { selector: ".journey-nav__counter" })).not.toBeInTheDocument();
  });

  it("explains how to seed DEMO-001 when it does not exist", async () => {
    install({ status: 404, body: { error: "not_found", message: "Participant not found", detail: null, correlation_id: null } });
    renderAt("/demo");
    expect(await screen.findByText(/DEMO-001 has not been seeded in this database/)).toBeInTheDocument();
    expect(screen.getByText(/seed_demo_participant\.py --dry-run/)).toBeInTheDocument();
  });
});
