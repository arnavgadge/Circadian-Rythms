import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TrajectoryChart } from "../TrajectoryChart";
import type { CircadianHistoryEntry } from "../../api/types";

function entry(date: string, clock: string | null): CircadianHistoryEntry {
  return {
    date,
    biological_clock: clock,
    confidence_score: 80,
    confidence_label: "high",
    alignment_score: 65,
    disagreement_regime: "normal",
    prediction_status: "success",
  };
}

// --- 18. Empty history ---
describe("TrajectoryChart", () => {
  it("shows a graceful message with no history", () => {
    render(<TrajectoryChart entries={[]} />);
    expect(screen.getByText(/no history is available yet/i)).toBeInTheDocument();
  });

  // --- 15. Midnight-crossing trajectory (rendered continuously, not as a gap) ---
  it("renders a midnight-crossing clock trajectory as one continuous accessible description", () => {
    const entries = [entry("2026-06-03", "00:10"), entry("2026-06-02", "23:55"), entry("2026-06-01", "23:40")];
    render(<TrajectoryChart entries={entries} />);
    const svg = screen.getByRole("img");
    expect(svg).toBeInTheDocument();
    expect(svg.tagName.toLowerCase()).toBe("svg");
  });
});
