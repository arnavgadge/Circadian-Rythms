import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RecommendationCard } from "../RecommendationCard";
import { buildRecommendation } from "../../test/fixtures";

// --- 9. Primary recommendation ---
describe("RecommendationCard", () => {
  it("shows the primary recommendation with target and expected improvement", () => {
    render(<RecommendationCard recommendation={buildRecommendation()} />);
    expect(screen.getByText("This week's primary focus")).toBeInTheDocument();
    expect(screen.getByText("Try stopping screens by 12:00 AM.")).toBeInTheDocument();
    expect(screen.getByText("12:00 AM", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText(/15 min/)).toBeInTheDocument();
  });

  // --- 10. Supporting nudges ---
  it("shows at most two supporting nudges, never three equal-weight recommendations", () => {
    const recommendation = buildRecommendation({
      supporting: [
        { intervention_type: "light", text: "Morning light before 9:00 AM", target_display: null, expected_improvement_minutes: null, expected_improvement_source: null },
        { intervention_type: "meal", text: "Finish dinner by 10:00 PM", target_display: null, expected_improvement_minutes: null, expected_improvement_source: null },
        { intervention_type: "exercise", text: "A third nudge that should not render", target_display: null, expected_improvement_minutes: null, expected_improvement_source: null },
      ],
    });
    render(<RecommendationCard recommendation={recommendation} />);
    expect(screen.getByText("Supporting nudges")).toBeInTheDocument();
    expect(screen.getByText("Morning light before 9:00 AM")).toBeInTheDocument();
    expect(screen.getByText("Finish dinner by 10:00 PM")).toBeInTheDocument();
    expect(screen.queryByText("A third nudge that should not render")).not.toBeInTheDocument();
  });

  // --- 11. Recommendation suppression ---
  it("renders nothing when the recommendation is suppressed by the safety layer", () => {
    const { container } = render(<RecommendationCard recommendation={buildRecommendation({ suppressed: true, available: false, primary: null })} />);
    expect(container).toBeEmptyDOMElement();
  });
});
