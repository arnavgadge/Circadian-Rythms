import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AlignmentScore } from "../AlignmentScore";
import { buildStatus } from "../../test/fixtures";

// --- 2. Alignment score ---
describe("AlignmentScore", () => {
  it("shows the score alongside phase and behavioral sub-scores, never alone", () => {
    render(<AlignmentScore alignment={buildStatus().alignment} />);
    expect(screen.getByText("68")).toBeInTheDocument();
    expect(screen.getByText("Phase alignment")).toBeInTheDocument();
    expect(screen.getByText("72")).toBeInTheDocument();
    expect(screen.getByText("Behavioral alignment")).toBeInTheDocument();
    expect(screen.getByText("62")).toBeInTheDocument();
  });

  it("frames the score as personal alignment, not a general health verdict", () => {
    render(<AlignmentScore alignment={buildStatus().alignment} />);
    expect(screen.getByText(/your own estimated circadian phase/i)).toBeInTheDocument();
  });
});
