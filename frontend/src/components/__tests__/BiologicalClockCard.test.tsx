import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BiologicalClockCard } from "../BiologicalClockCard";
import { buildStatus } from "../../test/fixtures";

// --- 1. Biological clock card ---
describe("BiologicalClockCard", () => {
  it("shows the estimated biological clock, chronotype, and boundary note", () => {
    render(<BiologicalClockCard status={buildStatus()} />);
    expect(screen.getByText("Estimated Biological Clock")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("11:48 PM");
    expect(screen.getByText(/Late/)).toBeInTheDocument();
    expect(screen.getByText("Estimated from behavioral patterns. Not a clinical measurement.")).toBeInTheDocument();
    expect(screen.queryByText(/clinical dlmo/i)).not.toBeInTheDocument();
  });

  // --- 5. Low-confidence approximate display ---
  it("shows an approximate marker and qualifier for low confidence", () => {
    render(
      <BiologicalClockCard
        status={buildStatus({
          approximate: true,
          confidence: { score: 45, label: "low", approximate: true },
          qualifier_message: "Approximate estimate — complete more data for better accuracy.",
        })}
      />,
    );
    expect(screen.getByText(/~11:48 PM/)).toBeInTheDocument();
    expect(screen.getByText(/Approximate estimate/)).toBeInTheDocument();
  });

  // --- 6. No-prediction display ---
  it("never fabricates a clock value when prediction is unavailable", () => {
    render(
      <BiologicalClockCard
        status={buildStatus({
          prediction_available: false,
          biological_clock: null,
          qualifier_message: "Not enough reliable data was available.",
        })}
      />,
    );
    expect(screen.getByText(/Not enough data for today's estimate/)).toBeInTheDocument();
    expect(screen.queryByText("11:48 PM")).not.toBeInTheDocument();
  });
});
