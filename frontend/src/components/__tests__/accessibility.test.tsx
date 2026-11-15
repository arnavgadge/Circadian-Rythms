import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { Sidebar } from "../layout/Sidebar";
import { BiologicalClockCard } from "../BiologicalClockCard";
import { buildStatus } from "../../test/fixtures";

// --- 20. Accessibility basics ---
describe("accessibility", () => {
  it("Sidebar exposes a labeled navigation landmark reachable by keyboard", async () => {
    render(
      <MemoryRouter>
        <Sidebar participantId={1} devMode={false} onToggleDevMode={vi.fn()} />
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
        <Sidebar participantId={null} devMode={false} onToggleDevMode={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("checkbox", { name: /research mode/i })).toBeInTheDocument();
  });

  it("Sidebar marks the current page and lists every participant section", () => {
    render(
      <MemoryRouter initialEntries={["/history/1"]}>
        <Sidebar participantId={1} devMode={false} onToggleDevMode={vi.fn()} />
      </MemoryRouter>,
    );
    const nav = screen.getByRole("navigation", { name: /main/i });
    for (const name of ["Dashboard", "Log Behavior", "History", "Interventions"]) {
      expect(within(nav).getByRole("link", { name })).toBeInTheDocument();
    }
    expect(within(nav).getByRole("link", { name: "History" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current");
  });
});
