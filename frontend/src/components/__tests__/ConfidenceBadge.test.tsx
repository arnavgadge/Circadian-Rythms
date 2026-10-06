import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConfidenceBadge } from "../ConfidenceBadge";

// --- 4. Confidence display ---
describe("ConfidenceBadge", () => {
  it("shows a label and score together for high confidence", () => {
    render(<ConfidenceBadge confidence={{ score: 84, label: "high", approximate: false }} />);
    expect(screen.getByText("High")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveAccessibleName(expect.stringContaining("84"));
  });

  it("communicates confidence without color alone (text label always present)", () => {
    render(<ConfidenceBadge confidence={{ score: 45, label: "low", approximate: true }} />);
    expect(screen.getByText("Low")).toBeInTheDocument();
  });
});
