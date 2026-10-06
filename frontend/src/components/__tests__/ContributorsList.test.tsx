import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ContributorsList } from "../ContributorsList";
import { buildStatus } from "../../test/fixtures";

// --- 7. Contributor rendering ---
describe("ContributorsList", () => {
  it("renders the top contributors with non-causal language", () => {
    render(<ContributorsList contributors={buildStatus().contributors} />);
    expect(screen.getByText(/Evening screens/)).toBeInTheDocument();
    expect(screen.getByText(/Morning light/)).toBeInTheDocument();
    expect(screen.getByText(/Social jetlag/)).toBeInTheDocument();
    // "cause" may legitimately appear in a negation ("not a proven ... cause");
    // what must never appear is an affirmative causal claim.
    expect(screen.queryByText(/\bcaused\b/i)).not.toBeInTheDocument();
    expect(screen.getByText(/modeled influence/i)).toBeInTheDocument();
  });

  // --- 8. Anomaly rendering (kept visually/structurally separate) ---
  it("shows today's anomaly as a distinct note on the affected contributor only", () => {
    render(<ContributorsList contributors={buildStatus().contributors} />);
    const anomalyNotes = screen.getAllByText(/today's pattern was unusual/i);
    expect(anomalyNotes).toHaveLength(1); // only the flagged contributor (evening_screen)
  });

  it("shows a graceful empty state with no contributors", () => {
    render(<ContributorsList contributors={[]} />);
    expect(screen.getByText(/no contributor data/i)).toBeInTheDocument();
  });
});
