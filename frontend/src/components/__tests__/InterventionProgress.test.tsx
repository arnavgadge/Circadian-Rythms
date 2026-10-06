import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { InterventionProgress } from "../InterventionProgress";
import type { InterventionHistoryEntry } from "../../api/types";

function entry(overrides: Partial<InterventionHistoryEntry>): InterventionHistoryEntry {
  return {
    intervention_log_id: 1,
    intervention_code: "SCREEN",
    intervention_type: "screen",
    log_date: "2026-06-01",
    target_display: "12:00 AM",
    actual_display: "11:50 PM",
    compliance_degree: 0.9,
    compliance_binary: true,
    observation_status: "observed",
    measurement_phase: 1,
    effect_estimate: -16,
    ...overrides,
  };
}

// --- 13. Intervention progress ---
describe("InterventionProgress", () => {
  it("shows compliant-day count and an observed change with a non-causal caveat", () => {
    render(
      <InterventionProgress
        entries={[entry({ intervention_log_id: 1, compliance_binary: true }), entry({ intervention_log_id: 2, compliance_binary: false })]}
      />,
    );
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
    expect(screen.getByText("Observed change")).toBeInTheDocument();
    expect(screen.getByText(/16 min earlier/)).toBeInTheDocument();
    expect(screen.getByText(/other behaviors also changed/i)).toBeInTheDocument();
  });

  it("shows a graceful empty state with no intervention history", () => {
    render(<InterventionProgress entries={[]} />);
    expect(screen.getByText(/no intervention history yet/i)).toBeInTheDocument();
  });
});
