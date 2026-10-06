import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Onboarding } from "../Onboarding";

afterEach(() => {
  vi.unstubAllGlobals();
});

async function advanceToConfirmStep(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: /get started/i }));
  await user.click(screen.getByLabelText(/i understand/i));
  await user.click(screen.getByRole("button", { name: /continue/i }));
  await user.click(screen.getByRole("button", { name: /continue/i }));
}

// --- 19. Onboarding validation ---
describe("Onboarding", () => {
  it("keeps Finish disabled until a participant code is entered", async () => {
    const user = userEvent.setup();
    render(<Onboarding onComplete={vi.fn()} />);

    await advanceToConfirmStep(user);

    const finishButton = screen.getByRole("button", { name: /finish/i });
    expect(finishButton).toBeDisabled();

    await user.type(screen.getByLabelText(/choose a participant code/i), "P000123");
    expect(finishButton).toBeEnabled();
  });

  it("submits onboarding and shows the confirmation step on success", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ participant_id: 7, participant_code: "P000123", status: "active", note: "Welcome." }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const onComplete = vi.fn();
    const user = userEvent.setup();
    render(<Onboarding onComplete={onComplete} />);

    await advanceToConfirmStep(user);
    await user.type(screen.getByLabelText(/choose a participant code/i), "P000123");
    await user.click(screen.getByRole("button", { name: /finish/i }));

    expect(await screen.findByText(/you're all set, P000123/i)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("shows a friendly error state if onboarding submission fails", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: "conflict", message: "A participant with this code already exists", detail: null, correlation_id: null }), {
        status: 409,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<Onboarding onComplete={vi.fn()} />);

    await advanceToConfirmStep(user);
    await user.type(screen.getByLabelText(/choose a participant code/i), "P000123");
    await user.click(screen.getByRole("button", { name: /finish/i }));

    expect(await screen.findByText(/already completed/i)).toBeInTheDocument();
  });
});
