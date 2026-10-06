import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ClockVisualization } from "../ClockVisualization";

// --- 14. Circular clock rendering ---
describe("ClockVisualization", () => {
  it("renders an accessible 24-hour clock face with a text alternative for every marker", () => {
    render(
      <ClockVisualization
        markers={[
          { key: "dlmo", label: "Estimated biological clock", value: "23:48", shape: "diamond", colorVar: "--color-accent" },
          { key: "ideal", label: "Ideal sleep onset", value: "01:48", shape: "circle", colorVar: "--color-good" },
          { key: "actual", label: "Actual recent sleep onset", value: "02:10", shape: "square", colorVar: "--color-moderate" },
        ]}
      />,
    );
    const svg = screen.getByRole("img");
    expect(svg).toHaveAccessibleName(expect.stringContaining("11:48 PM"));
    expect(screen.getByText("Estimated biological clock")).toBeInTheDocument();
    expect(screen.getByText("1:48 AM")).toBeInTheDocument();
    expect(screen.getByText("2:10 AM")).toBeInTheDocument();
  });

  it("handles a midnight-adjacent marker value without error", () => {
    render(<ClockVisualization markers={[{ key: "dlmo", label: "Estimated biological clock", value: "00:05", shape: "diamond", colorVar: "--color-accent" }]} />);
    expect(screen.getByText("12:05 AM")).toBeInTheDocument();
  });

  it("shows a dash for an unavailable marker rather than fabricating a position", () => {
    render(<ClockVisualization markers={[{ key: "dlmo", label: "Estimated biological clock", value: null, shape: "diamond", colorVar: "--color-accent" }]} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
