import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SafetyBanner } from "../SafetyBanner";
import { buildRecommendation } from "../../test/fixtures";

// --- 12. Safety banner ---
describe("SafetyBanner", () => {
  it("renders nothing when there is no active safety flag", () => {
    const { container } = render(
      <SafetyBanner safety={{ active: false, highest_severity: null, recommendation_suppressed: false, flag_types: [] }} recommendation={buildRecommendation()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a calm pattern note for MODERATE severity, without a diagnosis", () => {
    render(
      <SafetyBanner
        safety={{ active: true, highest_severity: "MODERATE", recommendation_suppressed: false, flag_types: ["persistent_late_phase"] }}
        recommendation={buildRecommendation()}
      />,
    );
    expect(screen.getByText("Pattern note")).toBeInTheDocument();
    expect(screen.getByText("This is not a diagnosis.")).toBeInTheDocument();
  });

  it("shows a prominent safety message for HIGH severity, referencing professional evaluation", () => {
    render(
      <SafetyBanner
        safety={{ active: true, highest_severity: "HIGH", recommendation_suppressed: true, flag_types: ["continuous_dlmo_drift"] }}
        recommendation={buildRecommendation({
          suppressed: true,
          available: false,
          primary: null,
          safety_message: "Given your recent pattern, consider speaking with a healthcare professional rather than continuing behavioral adjustments alone.",
        })}
      />,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/healthcare professional/i)).toBeInTheDocument();
    expect(screen.getByText(/cannot diagnose circadian rhythm disorders/i)).toBeInTheDocument();
  });
});
