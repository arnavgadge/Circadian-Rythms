import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { ErrorState } from "../ErrorState";

// --- 16. API error state ---
describe("ErrorState", () => {
  it("shows a friendly message for a 404 without leaking backend detail", () => {
    const error = new ApiError(404, "notfound", "Participant not found", "participant_id=999", "corr-123");
    render(<ErrorState error={error} />);
    expect(screen.getByText(/couldn't find that participant/i)).toBeInTheDocument();
    expect(screen.queryByText(/participant_id=999/)).not.toBeInTheDocument();
    expect(screen.getByText(/corr-123/)).toBeInTheDocument();
  });

  it("shows a friendly message for a network failure", () => {
    const error = new ApiError(0, "network_error", "Could not reach the CircadianIQ API.", null, null);
    render(<ErrorState error={error} />);
    expect(screen.getByText(/can't be reached/i)).toBeInTheDocument();
  });

  it("never renders a raw stack trace or generic Error object detail", () => {
    render(<ErrorState error={new Error("TypeError: Cannot read property 'x' of undefined at Object.<anonymous>")} />);
    expect(screen.queryByText(/TypeError/)).not.toBeInTheDocument();
  });

  it("invokes the retry callback when clicked", async () => {
    const onRetry = vi.fn();
    render(<ErrorState error={new ApiError(500, "internal_error", "boom", null, null)} onRetry={onRetry} />);
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
