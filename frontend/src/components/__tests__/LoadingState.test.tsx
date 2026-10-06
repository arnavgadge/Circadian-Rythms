import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LoadingState } from "../LoadingState";

// --- 17. Loading state ---
describe("LoadingState", () => {
  it("announces loading via an accessible live region with non-clinical wording", () => {
    render(<LoadingState label="Updating your circadian profile…" />);
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status).toHaveTextContent("Updating your circadian profile…");
  });
});
