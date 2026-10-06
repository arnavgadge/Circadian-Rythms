import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AlignmentBreakdown } from "../AlignmentBreakdown";
import { buildStatus } from "../../test/fixtures";

// --- 3. Alignment breakdown ---
describe("AlignmentBreakdown", () => {
  it("renders all five behavioral components with non-color-only status", () => {
    render(<AlignmentBreakdown components={buildStatus().alignment.components} />);
    for (const label of ["Sleep consistency", "Morning light", "Evening screen", "Meal timing", "Social jetlag"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    // Each bar has an accessible numeric label -- not conveyed by color alone.
    const bars = screen.getAllByRole("progressbar");
    expect(bars).toHaveLength(5);
    expect(bars[0]).toHaveAttribute("aria-valuenow");
  });

  it("renders nothing when no breakdown is available", () => {
    const { container } = render(<AlignmentBreakdown components={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
