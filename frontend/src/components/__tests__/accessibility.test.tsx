import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { Header } from "../Header";
import { BiologicalClockCard } from "../BiologicalClockCard";
import { buildStatus } from "../../test/fixtures";

// --- 20. Accessibility basics ---
describe("accessibility", () => {
  it("Header exposes a labeled navigation landmark reachable by keyboard", async () => {
    render(
      <MemoryRouter>
        <Header participantId={1} devMode={false} onToggleDevMode={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("navigation", { name: /main/i })).toBeInTheDocument();
    const user = userEvent.setup();
    await user.tab();
    expect(document.activeElement).toHaveAttribute("href"); // the CircadianIQ home link is focusable first
  });

  it("BiologicalClockCard uses a real heading rather than styled text alone", () => {
    render(<BiologicalClockCard status={buildStatus()} />);
    expect(screen.getByRole("heading", { level: 2 })).toBeInTheDocument();
  });

  it("Research-mode toggle is a real checkbox with an accessible label", () => {
    render(
      <MemoryRouter>
        <Header participantId={null} devMode={false} onToggleDevMode={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("checkbox", { name: /research mode/i })).toBeInTheDocument();
  });
});
